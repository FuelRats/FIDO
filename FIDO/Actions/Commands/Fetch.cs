using System;
using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using Flurl;
using Flurl.Http;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public class Fetch : Command
  {
    private const string url = "https://ipinfo.io/";
    private static readonly Regex regex = new Regex("!fetch (?<message>[0-9.:A-F-a-f]*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public Fetch(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override void OnMatch(string sender, string nick, string host, string filter, string message, string target)
    {
      IpFetchResult result = null;
      try
      {
        result = url.AppendPathSegment(message).GetJsonAsync<IpFetchResult>().Result;
      }
      catch (Exception e)
      {
        Console.WriteLine(e);
      }

      if (result == null)
      {
        return;
      }

      ReportToIrc(result.ToString());
    }

    // ReSharper disable once ClassNeverInstantiated.Local
    private class IpFetchResult
    {
      public override string ToString()
      {
        var location = string.Join(", ", new[] { City, Region, Country }.Where(x => !string.IsNullOrWhiteSpace(x)));
        return $"IP Information {Ip}: {location} ISP: {Org}";
      }

      // ReSharper disable MemberCanBePrivate.Local
      // ReSharper disable UnusedAutoPropertyAccessor.Local
      public string Ip { get; set; }
      public string City { get; set; }
      public string Region { get; set; }
      public string Country { get; set; }

      public string Org { get; set; }
      // ReSharper restore UnusedAutoPropertyAccessor.Local
      // ReSharper restore MemberCanBePrivate.Local
    }
  }
}