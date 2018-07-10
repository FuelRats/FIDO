using System;
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

      if (!int.TryParse(Environment.GetEnvironmentVariable("FloodProtectionRate"), out var rate))
      {
        rate = 3;
      }

      if (!int.TryParse(Environment.GetEnvironmentVariable("FloodProtectionTime"), out var per))
      {
        per = 3;
      }

      if (!int.TryParse(Environment.GetEnvironmentVariable("FloodProtectionDuration"), out var muteDuration))
      {
        muteDuration = 3;
      }

      floodProtector = new FloodProtector(ircLayer, rate, per, muteDuration);

      ircLayer.OnMessageReceived += IrcLayerOnOnMessageReceived;
      await ircLayer.Connect(server, port, useSsl, nickName, userName, realName);
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