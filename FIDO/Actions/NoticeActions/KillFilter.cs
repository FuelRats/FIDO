using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class KillFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex(@"Received KILL message for (?<nick>[A-Za-z0-9_´|\[\]]*)!(?<user>[A-Za-z0-9_´|\[\]]*)@(?<host>[A-Za-z0-9._\-]*) from (?<sender>[A-Za-z0-9_´|\[\]]*) Path: [A-Za-z0-9._\-]*![A-Za-z0-9_´|\[\]]* \((?<message>.*)\)$", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public KillFilter(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override ActionMode Mode => ActionMode.All;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      ReportToIrc($@"{"KILL".WrapWithColour(Colours.LightRed)} {nick} ({host}) was killed by {sender} with message: {message}");
    }
  }
}