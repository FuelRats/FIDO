using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Actions.ChannelActions.Flooding;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public class Unmute : Command
  {
    private static readonly Regex regex = new Regex(@"^!unmute (?<nick>[A-Za-z0-9_´|\[\]]+)", RegexOptions.IgnoreCase);
    private readonly IrcLayer irc;

    public Unmute(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      this.irc = irc;
    }

    protected override ActionMode Mode => ActionMode.OnlyAdmins;

    protected override Regex Regex => regex;

    protected override void OnMatch(IrcMessageEventArgs ircMessage, string sender, string nick, string host, string filter, string message, string target)
    {
      foreach (var ircMessageTarget in ircMessage.Targets)
      {
        var channel = ircMessageTarget.Name;
        var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
        var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == nick);
        FloodProtector.Instance.UnmuteUser(ircChannelUser);
      }
    }
  }
}