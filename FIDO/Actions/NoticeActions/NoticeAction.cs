using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;

namespace FIDO.Actions.NoticeActions
{
  public abstract class NoticeAction : Action
  {
    protected NoticeAction(IrcLayer irc, NexmoClient nexmo)
      : base(irc, nexmo)
    {
    }

    protected abstract Regex Regex { get; }

    public static IEnumerable<NoticeAction> GetAll(IrcLayer irc, NexmoClient nexmo)
    {
      yield return new BanFilter(irc, nexmo);
      yield return new ExpireFilter(irc, nexmo);
      yield return new FailedOperFilter(irc, nexmo);
      yield return new KillFilter(irc, nexmo);
      yield return new OperServFilter(irc, nexmo);
      yield return new SpamFilter(irc, nexmo);
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