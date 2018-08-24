using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Fastenshtein;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.NoticeActions
{
  public class SessionTracker : NoticeAction
  {
    private readonly ConcurrentDictionary<string, HashSet<NickInfo>> nicksOnIps;

    public SessionTracker(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      nicksOnIps = new ConcurrentDictionary<string, HashSet<NickInfo>>();
    }

    protected override Regex Regex => new Regex(@"(Client connecting: (?<nick>[A-Za-z0-9_´|\[\]]*) \((?<user>[A-Za-z0-9_´|\[\]]*)@(?<host>[A-Za-z0-9.:_\-]*)\) \[(?<filter>[0-9.:A-F-a-f]*)\])", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    protected override ActionMode Mode => ActionMode.All;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      var ip = filter;
      nick = nick.Replace("[", string.Empty);
      nick = nick.Replace("]", string.Empty);

      var nicks = nicksOnIps.GetOrAdd(ip, new HashSet<NickInfo>());
      var nickInfo = new NickInfo(nick);
      nicks.Add(nickInfo);

      var previousNicks = nicks.Where(x => Levenshtein.Distance(nickInfo.LowerCaseNick, x.LowerCaseNick) >= 4 && x.Used == false).ToArray();
      if (previousNicks.Length == 0) { return; }

      ReportToIrc($@"{"CLONES".WrapWithColour(Colours.LightRed)} {nick} has connected from {ip}. Previous names: {string.Join(", ", previousNicks.Select(x => x.Nick))}");

      foreach (var info in nicks)
      {
        info.Used = true;
      }
    }

    private class NickInfo : IEquatable<NickInfo>
    {
      public NickInfo(string nick)
      {
        Nick = nick;
        LowerCaseNick = nick.ToLowerInvariant();
        Used = false;
      }

      public string Nick { get; }
      public string LowerCaseNick { get; }
      public bool Used { get; set; }

      public bool Equals(NickInfo other)
      {
        return string.Equals(LowerCaseNick, other?.LowerCaseNick);
      }

      public override bool Equals(object obj)
      {
        if (ReferenceEquals(null, obj))
        {
          return false;
        }

        return obj is NickInfo other && Equals(other);
      }

      public override int GetHashCode()
      {
        return LowerCaseNick != null ? LowerCaseNick.GetHashCode() : 0;
      }
    }
  }
}