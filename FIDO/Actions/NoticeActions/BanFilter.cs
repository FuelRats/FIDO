using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class BanFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex("(?<message>Global [A-Z]*-Line added .*)|(?<message>[A-Z]*-Line added .*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public BanFilter(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override ActionMode Mode => ActionMode.All;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      ReportToIrc($"{"NETWORK BAN".WrapWithColour(Colours.LightRed)} {message}");
    }
  }
}