using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public class Debug : Command
  {
    private static readonly Regex regex = new Regex(@"^!debug (?<nick>[A-Za-z0-9_´|\[\]]+)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private readonly IrcLayer irc;

    public Debug(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      this.irc = irc;
    }

    protected override ActionMode Mode => ActionMode.OnlyAdmins;

    protected override Regex Regex => regex;

    protected override void OnMatch(IrcMessageEventArgs ircMessage, string sender, string nick, string host, string filter, string message, string target)
    {
      var user = irc.Client.Users.SingleOrDefault(u => u.NickName == nick);
      if (user == null)
      {
        ReportToIrc("User " + nick + " not found");
        return;
      }

      var ircChannels = user.GetChannelUsers().Select(x => x).ToList();
      var channels = string.Join(", ", ircChannels.Select(x => x.Modes + x.Channel.Name));
      ReportToIrc("User " + nick + ", hostname " + user.HostName + " is in channels: " + channels);
    }
  }
}