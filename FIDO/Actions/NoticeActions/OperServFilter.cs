using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class OperServFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex("from OperServ: (?<message>.*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public OperServFilter(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      if (message.Contains("now an IRC operator"))
      {
        return;
      }

      ReportToIrc($"{"OperServ".WrapWithColour(Colours.LightRed)} {message}");
    }
  }
}