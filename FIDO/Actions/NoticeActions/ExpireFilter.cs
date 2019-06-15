using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class ExpireFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex("(?<message>Expiring Global [A-Z]*:Line .*)|(?<message>Expiring [A-Z]*:Line .*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public ExpireFilter(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override ActionMode Mode => ActionMode.All;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      ReportToIrc($"{"Expiring".WrapWithColour(Colours.LightRed)} {message}");
    }
  }
}