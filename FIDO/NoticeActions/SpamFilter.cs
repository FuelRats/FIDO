using System;
using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;

namespace FIDO.NoticeActions
{
  public class SpamFilter : NoticeAction
  {
    private static readonly Regex spamfilterMatch = new Regex(@"/\[Spamfilter\] ([A - Za - z0 - 9_´|\[\]]*)!([A - Za - z0 - 9_´|\[\]]*)@([A - Za - z0 - 9._\-]*) matches filter '(.*)': \[([A-Za-z0-9]* ([A - Za - z0 - 9#_`\[\]]*): .*)]", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private readonly string operChannel;

    public SpamFilter(IrcLayer irc)
      : base(irc)
    {
      operChannel = Environment.GetEnvironmentVariable("OperChannel");
      if (string.IsNullOrWhiteSpace(operChannel))
      {
        operChannel = "opers";
      }
    }

    protected override Regex Regex => spamfilterMatch;

    protected override void OnMatch(string capture, string nick, string user, string host, string filter, string text, string target)
    {
      if (filter == "*opsignal*" || filter == "*opssignal*")
      {
        irc.Client.LocalUser.SendMessage(operChannel, $@"{"OPSIGNAL".WrapWithColour(Colours.LightRed)} by {nick} in channel / query {target}. Original message: ""{text}""");
        // TODO SMS client.textNotification(`OPSIGNAL by ${ nick} in channel / query ${ target}. Original message: ${ message}`)
      }
      else
      {
        irc.Client.LocalUser.SendMessage(operChannel, $"{"SPAMFILTER".WrapWithColour(Colours.LightRed)} triggered by {nick} in channel / query {target}.");
      }
    }
  }
}