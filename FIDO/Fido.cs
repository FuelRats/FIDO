using System;
using System.Linq;
using System.Threading.Tasks;
using FIDO.FloodProtections;
using IrcDotNet;

namespace FIDO
{
  public class Fido
  {
    private IrcLayer ircLayer;
    private FloodProtector floodProtector;

    public async Task Run()
    {
      var nickName = Environment.GetEnvironmentVariable("NickName");
      var userName = Environment.GetEnvironmentVariable("UserName");
      var realName = Environment.GetEnvironmentVariable("RealName");
      var channels = Environment.GetEnvironmentVariable("Channels").Split(',').Select(x=>x.Trim()).ToList();

      ircLayer = new IrcLayer();

      var server = Environment.GetEnvironmentVariable("Server");
      if (string.IsNullOrWhiteSpace(server))
      {
        throw new Exception("No server given");
      }

      var hasPort = int.TryParse(Environment.GetEnvironmentVariable("Port"), out var port);
      bool.TryParse(Environment.GetEnvironmentVariable("UseSsl"), out var useSsl);
      //bool.TryParse(Environment.GetEnvironmentVariable("AcceptInvalidCerts"), out var acceptInvalidCerts);

      if (!hasPort)
      {
        port = useSsl ? 6697 : 6667;
      }

      floodProtector = new FloodProtector(ircLayer);

      ircLayer.OnMessageReceived += IrcLayerOnOnMessageReceived;
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

    private void IrcLayerOnOnMessageReceived(object sender, IrcMessageEventArgs ircMessageEventArgs)
    {
      foreach (var ircMessageTarget in ircMessageEventArgs.Targets)
      {
        floodProtector.Check(ircMessageTarget.Name, ircMessageEventArgs.Source.Name);
      }

      // commands here
    }
  }
}