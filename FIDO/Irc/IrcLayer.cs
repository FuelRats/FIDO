using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Irc
{
  public class IrcLayer
  {
    private readonly IConfiguration configuration;
    private readonly Dictionary<string, BlockingCollection<IrcMessageEventArgs>> messageQueues = new Dictionary<string, BlockingCollection<IrcMessageEventArgs>>();
    private readonly CancellationTokenSource cancellationTokenSource = new CancellationTokenSource();
    private readonly IList<Task> messageDispatchers = new List<Task>();

    private StandardIrcClient irc;
    private List<string> channels;

    public IrcLayer(IConfiguration configuration)
    {
      this.configuration = configuration;
    }

    public IrcClient Client => irc;

    public event EventHandler<IrcMessageEventArgs> OnMessageReceived;
    public event EventHandler<IrcMessageEventArgs> OnNoticeReceived;
    public event EventHandler<IrcMessageEventArgs> OnQueryReceived;
    public event EventHandler Connected;
    public event EventHandler Disconnected;

    public async Task Connect(string server, int port, bool useSsl, string nickName, string userName, string realname, List<string> channelsToJoin)
    {
      channels = channelsToJoin;
      irc = new StandardIrcClient
      {
        FloodPreventer = new IrcStandardFloodPreventer(3, 5000)
      };

      irc.RawMessageSent += IrcOnRawMessageSent;
      irc.Error += OnIrcOnOnError;
      irc.Registered += IrcOnRegistered;
      irc.Disconnected += IrcOnDisconnected;

      try
      {
        var registrationInfo = new IrcUserRegistrationInfo { NickName = nickName, UserName = userName, RealName = realname };
        var ipAddresses = await Dns.GetHostAddressesAsync(server);
        var ipAddress = ipAddresses.First(x => x.AddressFamily == AddressFamily.InterNetwork);
        Console.WriteLine($"Resolved IP: {ipAddress}");
        var ipEndPoint = new IPEndPoint(ipAddress, port);
        irc.Connect(ipEndPoint, useSsl, registrationInfo);
      }
      catch (Exception e)
      {
        Console.WriteLine(e);
      }
    }

    public void Send(string cmd)
    {
      if (cmd == null)
      {
        return;
      }

      if (irc != null && irc.IsConnected)
      {
        if (cmd.StartsWith("/list"))
        {
          var pos = cmd.IndexOf(" ", StringComparison.Ordinal);
          string channel = null;
          if (pos != -1)
          {
            channel = cmd.Substring(pos + 1);
          }

          var channelInfos = irc.Channels.Where(x => x.Name == channel).ToList();
          Console.WriteLine("channel count: {0}", channelInfos.Count);
          foreach (var channelInfo in channelInfos)
          {
            Console.WriteLine("channel: {0} user count: {1} topic: {2}", channelInfo.Name, channelInfo.Users.Count, channelInfo.Topic);
          }
        }
        else
        {
          irc.SendRawMessage(cmd);
        }
      }
    }

    public async Task Disconnect()
    {
      if (irc?.IsConnected != true)
      {
        return;
      }

      try
      {
        {
          cancellationTokenSource.Cancel();
          await Task.WhenAll(messageDispatchers);
        }

        irc.Quit("QQ");
      }
      catch (Exception)
      {
        // ignored
      }
    }

    private void IrcOnDisconnected(object sender, EventArgs e)
    {
      if (irc != null)
      {
        irc.RawMessageSent -= IrcOnRawMessageSent;
        irc.Error -= OnIrcOnOnError;
        irc.Registered -= IrcOnRegistered;
        irc.Disconnected -= IrcOnDisconnected;

        if (irc.LocalUser != null)
        {
          irc.LocalUser.NoticeReceived -= IrcClient_LocalUser_NoticeReceived;
          irc.LocalUser.MessageReceived -= IrcClient_LocalUser_MessageReceived;
          irc.LocalUser.JoinedChannel -= IrcClient_LocalUser_JoinedChannel;
          irc.LocalUser.LeftChannel -= IrcClient_LocalUser_LeftChannel;
        }

        foreach (var channel in irc.Channels)
        {
          channel.MessageReceived -= IrcClient_Channel_MessageReceived;
          //e.Channel.UserJoined -= IrcClient_Channel_UserJoined;
          //e.Channel.UserLeft -= IrcClient_Channel_UserLeft;
          //e.Channel.NoticeReceived -= IrcClient_Channel_NoticeReceived;
        }
      }

      Disconnected?.Invoke(sender, e);
    }

    private void DispatchMessages(BlockingCollection<IrcMessageEventArgs> queue, EventHandler<IrcMessageEventArgs> eventHandler)
    {
      try
      {
        while (!cancellationTokenSource.IsCancellationRequested && !queue.IsCompleted)
        {
          var messages = queue.GetConsumingEnumerable(cancellationTokenSource.Token);
          foreach (var message in messages)
          {
            eventHandler?.Invoke(this, message);
          }
        }
      }
      catch (OperationCanceledException)
      {
      }
    }

    private void IrcOnRegistered(object sender, EventArgs e)
    {
      Connected?.Invoke(sender, EventArgs.Empty);
      var client = (IrcClient) sender;

      var noticeQueue = new BlockingCollection<IrcMessageEventArgs>();
      messageQueues["Notice"] = noticeQueue;
      messageDispatchers.Add(Task.Run(() => DispatchMessages(noticeQueue, OnNoticeReceived)));

      var queryQueue = new BlockingCollection<IrcMessageEventArgs>();
      messageQueues["Query"] = queryQueue;
      messageDispatchers.Add(Task.Run(() => DispatchMessages(queryQueue, OnQueryReceived)));

      client.LocalUser.NoticeReceived += IrcClient_LocalUser_NoticeReceived;
      client.LocalUser.MessageReceived += IrcClient_LocalUser_MessageReceived;
      client.LocalUser.JoinedChannel += IrcClient_LocalUser_JoinedChannel;
      client.LocalUser.LeftChannel += IrcClient_LocalUser_LeftChannel;

      client.LocalUser.SendMessage("nickserv", $"IDENTIFY {configuration["NickservPassword"]}");

      var operLine = configuration["OperLine"];
      var operLinePassword = configuration["OperLinePassword"];
      if (!string.IsNullOrWhiteSpace(operLine) && !string.IsNullOrWhiteSpace(operLinePassword))
      {
        client.SendRawMessage($"OPER {operLine} {operLinePassword}");
      }

      if (!channels.Any())
      {
        client.Channels.Join(channels);
      }
    }

    private void IrcClient_LocalUser_NoticeReceived(object sender, IrcMessageEventArgs e)
    {
      Console.WriteLine($"Notice received: {e.Text}");
      messageQueues["Notice"].Add(e);
    }

    private void IrcClient_LocalUser_LeftChannel(object sender, IrcChannelEventArgs e)
    {
      messageQueues[e.Channel.Name].CompleteAdding();

      //e.Channel.UserJoined -= IrcClient_Channel_UserJoined;
      //e.Channel.UserLeft -= IrcClient_Channel_UserLeft;
      e.Channel.MessageReceived -= IrcClient_Channel_MessageReceived;
      //e.Channel.NoticeReceived -= IrcClient_Channel_NoticeReceived;
    }

    private void IrcClient_LocalUser_JoinedChannel(object sender, IrcChannelEventArgs e)
    {
      var queue = new BlockingCollection<IrcMessageEventArgs>();
      messageQueues[e.Channel.Name] = queue;
      messageDispatchers.Add(Task.Run(() => DispatchMessages(queue, OnMessageReceived)));

      //e.Channel.UserJoined += IrcClient_Channel_UserJoined;
      //e.Channel.UserLeft += IrcClient_Channel_UserLeft;
      e.Channel.MessageReceived += IrcClient_Channel_MessageReceived;
      //e.Channel.NoticeReceived += IrcClient_Channel_NoticeReceived;
    }

    private void IrcClient_Channel_MessageReceived(object sender, IrcMessageEventArgs e)
    {
      foreach (var ircMessageTarget in e.Targets)
      {
        Console.WriteLine($"Message received: {e.Text} in channel {ircMessageTarget.Name}");
        var blockingCollection = messageQueues[ircMessageTarget.Name];
        blockingCollection.Add(e);
      }
    }

    private void IrcClient_LocalUser_MessageReceived(object sender, IrcMessageEventArgs e)
    {
      Console.WriteLine($"Query received: {e.Text} from {e.Source.Name}");
      var blockingCollection = messageQueues["Query"];
      blockingCollection.Add(e);
    }

    private static void IrcOnRawMessageSent(object sender, IrcRawMessageEventArgs e)
    {
      if (e == null || e.RawContent.Contains("nickserv"))
      {
        return;
      }

      Console.WriteLine("Sent: " + e.RawContent);
    }

    private static void OnIrcOnOnError(object sender, IrcErrorEventArgs e)
    {
      Console.WriteLine("Error: " + e.Error);
    }
  }
}