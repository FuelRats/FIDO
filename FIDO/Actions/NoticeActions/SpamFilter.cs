using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class SpamFilter : NoticeAction
  {
    private static readonly Regex regex = new Regex(@"\[Spamfilter\] (?<nick>[A-Za-z0-9_´|\[\]]*)!(?<user>[A-Za-z0-9_´|\[\]]*)@(?<host>[A-Za-z0-9.:_\-]*) matches filter '(?<filter>.*)': \[(?<message>[A-Za-z0-9]* (?<target>[A-Za-z0-9#_`\[\]]*):.*)]", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public SpamFilter(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override ActionMode Mode => ActionMode.All;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      if (filter == "*opsignal*" || filter == "*opssignal*")
      {
        ReportToIrc($@"{"OPSIGNAL".WrapWithColour(Colours.LightRed)} by {nick} in channel / query {target}. Original message: ""{message}""");
        SendSms($"OPSIGNAL by {nick} in channel / query {target}. Original message: {message}");
      }
      else
      {
        ReportToIrc($"{"SPAMFILTER".WrapWithColour(Colours.LightRed)} triggered by {nick} in channel / query {target}.");
      }
    }
  }
}