using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.ChannelActions
{
  public class HighlightCount : ChannelAction
  {
    private static readonly Regex split = new Regex(@"\s+", RegexOptions.Compiled);
    private readonly int maxHighlightCount;

    public HighlightCount(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      if (!int.TryParse(configuration["MaxHighlightCount"], out maxHighlightCount))
      {
        maxHighlightCount = 5;
      }
    }

    protected override ActionMode Mode => ActionMode.OnlyUsers;

    protected override bool OnExecute(IrcMessageEventArgs ircMessage)
    {
      var words = split.Split(ircMessage.Text);
      var highlightCount = words.Select(GetUser).Distinct().Count(x => x != null);

      if (highlightCount >= maxHighlightCount)
      {
        var user = GetUser(ircMessage.Source.Name);
        Kill(user);
        ReportToIrc($"KILLED {user.NickName} ({user.HostName}) has been automatically killed for highlight spam in ${ircMessage.Targets.FirstOrDefault()?.Name}");
        return true;
      }

      return false;
    }
  }
}