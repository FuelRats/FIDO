using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;

namespace FIDO.Actions.NoticeActions
{
  public class FailedOperFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex("Failed OPER attempt (?<message>.*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public FailedOperFilter(IrcLayer irc, NexmoClient nexmo)
      : base(irc, nexmo)
    {
    }

    protected override Regex Regex => regex;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      ReportToIrc($"{"OPER FAILED".WrapWithColour(Colours.LightRed)} {message}");
    }
  }
}