using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.ChannelActions
{
  public class ZalgoProctection : ChannelAction
  {
    private const double threshold = 0.55D;
    private const double percentile = 0.75D;
    private static readonly Regex regex = new Regex(@"\[\p{Mn}\p{Me}\]+", RegexOptions.Compiled);
    private static readonly Regex split = new Regex(@"\s+", RegexOptions.Compiled);

    public ZalgoProctection(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    public override bool Execute(IrcMessageEventArgs ircMessage)
    {
      var isZalgo = IsZalgo(ircMessage.Text);
      if (isZalgo)
      {
        var user = GetUser(ircMessage.Source.Name);

        Kill(user);
        ReportToIrc($"KILLED {user.NickName} ({user.HostName}) has been automatically killed for posting harmful unicode characters in ${ircMessage.Targets.FirstOrDefault()?.Name}");
      }

      return isZalgo;
    }

    private bool IsZalgo(string message)
    {
      if (string.IsNullOrWhiteSpace(message))
      {
        return false;
      }

      message = message.Normalize(NormalizationForm.FormD);

      var scores = new List<int>();
      var words = split.Split(message);
      foreach (var word in words)
      {
        var banned = 0;
        foreach (var character in word)
        {
          if (regex.IsMatch(character.ToString()))
          {
            banned++;
          }
        }

        scores.Add(banned);
      }

      var d = Percentile(scores);
      return d > threshold;
    }

    private double Percentile(IList<int> vals)
    {
      if (vals.Count == 0)
      {
        return 0;
      }

      // Fudge anything over 100 to 1.0
      vals = vals.OrderBy(x => x).ToList();
      var i = vals.Count * percentile - 0.5;

      var floor = (int) i;

      if (Math.Abs(floor - i) < double.Epsilon)
      {
        return vals[floor];
      }

      // interpolated percentile -- using Estimation method
      var fract = i - floor;
      return (1 - fract) * vals[floor] + fract * vals[Math.Min(floor + 1, vals.Count - 1)];
    }
  }
}