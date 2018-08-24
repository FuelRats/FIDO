﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FIDO.Actions.ChannelActions;
using FIDO.Actions.Commands;
using FIDO.Actions.NoticeActions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO
{
  public class Fido
  {
    private readonly IConfiguration configuration;
    private readonly IList<NoticeAction> noticeActions = new List<NoticeAction>();
    private readonly IList<ChannelAction> channelActions = new List<ChannelAction>();
    private readonly IList<Command> channelCommands = new List<Command>();

    private IrcLayer ircLayer;
    private NexmoClient nexmo;

    public Fido(IConfiguration configuration)
    {
      this.configuration = configuration;
    }

    public bool IsConnected { get; private set; }

    public event EventHandler Disconnected;

    public async Task Run()
    {
      var nickName = configuration["NickName"];
      var userName = configuration["UserName"];
      var realName = configuration["RealName"];
      var channels = configuration["Channels"].Split(',').Select(x => x.Trim()).ToList();

      ircLayer = new IrcLayer(configuration);

      var server = configuration["Server"];
      if (string.IsNullOrWhiteSpace(server))
      {
        throw new Exception("No server given");
      }

      var hasPort = int.TryParse(configuration["Port"], out var port);
      bool.TryParse(configuration["UseSsl"], out var useSsl);

      if (!hasPort)
      {
        port = useSsl ? 6697 : 6667;
      }

      nexmo = new NexmoClient(configuration);
      noticeActions.AddRange(NoticeAction.GetAll(ircLayer, nexmo, configuration));
      channelActions.AddRange(ChannelAction.GetAll(ircLayer, nexmo, configuration));
      channelCommands.AddRange(Command.GetAll(ircLayer, nexmo, configuration));

      ircLayer.OnMessageReceived += IrcLayerOnOnMessageReceived;
      ircLayer.OnNoticeReceived += IrcLayerOnOnNoticeReceived;
      ircLayer.Disconnected += IrcLayerDisconnected;
      await ircLayer.Connect(server, port, useSsl, nickName, userName, realName, channels);
      IsConnected = true;
    }

    public void SendRawMessage(string rawMessage)
    {
      ircLayer.Send(rawMessage);
    }

    public async Task Disconnect()
    {
      await ircLayer.Disconnect();
    }

    private void IrcLayerDisconnected(object sender, EventArgs e)
    {
      IsConnected = false;
      Disconnected?.Invoke(sender, e);
    }

    private void IrcLayerOnOnNoticeReceived(object sender, IrcMessageEventArgs e)
    {
      foreach (var noticeAction in noticeActions)
      {
        if (noticeAction.ExecuteOnMatch(e))
        {
          return;
        }
      }
    }

    private void IrcLayerOnOnMessageReceived(object sender, IrcMessageEventArgs ircMessageEventArgs)
    {
      foreach (var channelAction in channelActions)
      {
        if (channelAction.Execute(ircMessageEventArgs))
        {
          return;
        }
      }

      foreach (var command in channelCommands)
      {
        if (command.ExecuteOnMatch(ircMessageEventArgs))
        {
          return;
        }
      }
    }
  }
}