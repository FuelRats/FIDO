using System.Linq;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions
{
  public abstract class Action
  {
    private readonly IrcLayer irc;
    private readonly NexmoClient nexmo;
    private readonly string reportChannel;

    protected Action(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
    {
      this.irc = irc;
      this.nexmo = nexmo;

      reportChannel = configuration["OperChannel"];
      if (string.IsNullOrWhiteSpace(reportChannel))
      {
        reportChannel = "#opers";
      }
    }

    protected void ReportToIrc(string message)
    {
      irc.Client.LocalUser.SendMessage(reportChannel, message);
    }

    protected void SendSms(string message)
    {
      nexmo.SendSms(message);
    }

    protected IrcUser GetUser(string name)
    {
      return irc.Client.Users.SingleOrDefault(x => x.NickName == name);
    }
  }
}