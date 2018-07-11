using System.Collections.Generic;
using System.Text.RegularExpressions;
using IrcDotNet;

namespace FIDO.NoticeActions
{
  public abstract class NoticeAction
  {
    protected readonly IrcLayer irc;

    protected NoticeAction(IrcLayer irc)
    {
      this.irc = irc;
    }

    protected abstract Regex Regex { get; }

    public static IEnumerable<NoticeAction> GetAll(IrcLayer irc)
    {
      yield return new SpamFilter(irc);
    }

    public bool ExecuteOnMatch(IrcMessageEventArgs message)
    {
      var match = Regex.Match(message.Text);

      if (!match.Success)
      {
        return false;
      }

      var capture = match.Groups[0].Value;
      var nick = match.Groups[1].Value;
      var user = match.Groups[2].Value;
      var host = match.Groups[3].Value;
      var filter = match.Groups[4].Value;
      var text = match.Groups[5].Value;
      var target = match.Groups[6].Value;

      OnMatch(capture, nick, user,host, filter, text, target);

      return true;
    }

    protected abstract void OnMatch(string capture, string nick, string user, string host, string filter, string text, string target);
  }
}