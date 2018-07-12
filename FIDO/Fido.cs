using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FIDO.Actions.ChannelActions;
using FIDO.Actions.NoticeActions;
using FIDO.Extensions;
using FIDO.FloodProtections;
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

    private IrcLayer ircLayer;
    private FloodProtector floodProtector;
    private NexmoClient nexmo;

    public Fido(IConfiguration configuration)
    {
      this.configuration = configuration;
    }

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
      floodProtector = new FloodProtector(ircLayer, configuration);
      noticeActions.AddRange(NoticeAction.GetAll(ircLayer, nexmo, configuration));
      channelActions.AddRange(ChannelAction.GetAll(ircLayer, nexmo, configuration));

      ircLayer.OnMessageReceived += IrcLayerOnOnMessageReceived;
      ircLayer.OnNoticeReceived += IrcLayerOnOnNoticeReceived;
      await ircLayer.Connect(server, port, useSsl, nickName, userName, realName, channels);
    }

    public void SendRawMessage(string rawMessage)
    {
      ircLayer.Send(rawMessage);
    }

    public async Task Disconnect()
    {
      await ircLayer.Disconnect();
    }

    private void IrcLayerOnOnNoticeReceived(object sender, IrcMessageEventArgs e)
    {
      foreach (var noticeAction in noticeActions)
      {
        if (noticeAction.ExecuteOnMatch(e))
        {
          break;
        }
      }
    }

    private void IrcLayerOnOnMessageReceived(object sender, IrcMessageEventArgs ircMessageEventArgs)
    {
      foreach (var ircMessageTarget in ircMessageEventArgs.Targets)
      {
        floodProtector.Check(ircMessageTarget.Name, ircMessageEventArgs.Source.Name);
      }

      foreach (var channelAction in channelActions)
      {
        if (channelAction.Execute(ircMessageEventArgs))
        {
          break;
        }
      }
    }
  }
}