using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;

namespace FIDO.Actions.NoticeActions
{
  public class BanFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex("(?<message>Global [A-Z]*:Line added .*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public BanFilter(IrcLayer irc, NexmoClient nexmo)
      : base(irc, nexmo)
    {
    }

    protected override Regex Regex => regex;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      ReportToIrc($"{"NETWORK BAN".WrapWithColour(Colours.LightRed)} {message}");
    }
  }
}