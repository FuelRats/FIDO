using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public class Join : Command
  {
    private static readonly Regex regex = new Regex("^!join", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private readonly IrcLayer irc;
    private readonly IConfiguration configuration;

    public Join(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      this.irc = irc;
      this.configuration = configuration;
    }

    protected override ActionMode Mode => ActionMode.OnlyAdmins;

    protected override Regex Regex => regex;

    protected override void OnMatch(IrcMessageEventArgs ircMessage, string sender, string nick, string host, string filter, string message, string target)
    {
      var parts = ircMessage.Text.Split(' ');
      if (parts.Length == 0 || parts.Length > 2 || !parts.Any(x => x.StartsWith("#")))
      {
        return;
      }

      var part0 = parts[0];
      var part1 = parts.Length == 2 ? parts[1] : string.Empty;

      var (save, channel) = NewMethod(part0, false, null);
      (save, channel) = NewMethod(part1, save, channel);

      irc.Client.Channels.Join(channel);
      if (save)
      {
        configuration["Channels"] = string.Join(',', configuration["Channels"], channel);
      }
    }

    private (bool save, string channel) NewMethod(string part, bool save, string channel)
    {
      switch (part)
      {
        case "save":
          save = true;
          break;
        default:
          channel = part;
          break;
      }

      return (save, channel);
    }
  }
}