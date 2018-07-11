using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using IrcDotNet;

namespace FIDO
{
  public class IrcLayer
  {
    private readonly Dictionary<string, BlockingCollection<IrcMessageEventArgs>> messageQueues = new Dictionary<string, BlockingCollection<IrcMessageEventArgs>>();
    private readonly CancellationTokenSource cancellationTokenSource = new CancellationTokenSource();
    private readonly IList<Task> messageDispatchers = new List<Task>();

    private StandardIrcClient irc;
    private List<string> channels;

    public IrcClient Client => irc;

    public event EventHandler<IrcMessageEventArgs> OnMessageReceived;
    public event EventHandler<IrcMessageEventArgs> OnNoticeReceived;

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

    private void DispatchMessages(BlockingCollection<IrcMessageEventArgs> queue, EventHandler<IrcMessageEventArgs> eventHandler)
    {
      while (!cancellationTokenSource.IsCancellationRequested && !queue.IsCompleted)
      {
        if (queue.TryTake(out var message))
        {
          try
          {
            eventHandler?.Invoke(this, message);
          }
          catch (Exception e)
          {
            Console.WriteLine(e);
          }
        }
      }
    }

    private void IrcOnRegistered(object sender, EventArgs e)
    {
      var client = (IrcClient) sender;

      var queue = new BlockingCollection<IrcMessageEventArgs>();
      messageQueues["Notice"] = queue;
      messageDispatchers.Add(Task.Run(() => DispatchMessages(queue, OnNoticeReceived)));

      client.LocalUser.NoticeReceived += IrcClient_LocalUser_NoticeReceived;
      client.LocalUser.MessageReceived += IrcClient_LocalUser_MessageReceived;
      client.LocalUser.JoinedChannel += IrcClient_LocalUser_JoinedChannel;
      client.LocalUser.LeftChannel += IrcClient_LocalUser_LeftChannel;

      client.LocalUser.SendMessage("nickserv", $"IDENTIFY {Environment.GetEnvironmentVariable("NickservPassword")}");
      client.Channels.Join(channels);
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
      var parts = e.Text.Split(' ');
      if (!parts.Any())
      {
        return;
      }

      switch (parts[0])
      {
        case "join" when parts.Length == 2:
          irc.Channels.Join(parts[1]);
          break;
        case "part" when parts.Length == 2:
          irc.Channels.Leave(parts.Skip(1), "Leaving channel! QQ");
          break;
        default:
          Console.WriteLine($"Unknown command: {parts[0]}");
          break;
      }
    }

    private static void IrcOnRawMessageSent(object sender, IrcRawMessageEventArgs e)
    {
      Console.WriteLine("Sent: " + e?.RawContent);
    }

    private static void OnIrcOnOnError(object sender, IrcErrorEventArgs e)
    {
      Console.WriteLine("Error: " + e.Error);
    }
  }
}