using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public abstract class Command : Action
  {
    protected Command(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected abstract Regex Regex { get; }

    public static IEnumerable<Command> GetAll(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
    {
      yield return new Fetch(irc, nexmo, configuration);
    }

    public bool ExecuteOnMatch(IrcMessageEventArgs ircMessageEventArgs)
    {
      var match = Regex.Match(ircMessageEventArgs.Text);

      if (!match.Success)
      {
        return false;
      }

      var sender = GetGroupValueByName(match, "sender");
      var nick = GetGroupValueByName(match, "nick");
      var host = GetGroupValueByName(match, "host");
      var filter = GetGroupValueByName(match, "filter");
      var message = GetGroupValueByName(match, "message");
      var target = GetGroupValueByName(match, "target");

      OnMatch(sender, nick, host, filter, message, target);

      return true;
    }

    protected abstract void OnMatch(string sender, string nick, string host, string filter, string message, string target);

    private static string GetGroupValueByName(Match match, string name)
    {
      var group = match.Groups.SingleOrDefault(x => x.Name == name);
      var value = group?.Value;
      return value;
    }
  }
}