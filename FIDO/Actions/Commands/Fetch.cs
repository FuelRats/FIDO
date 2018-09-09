using System;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using FIDO.Irc;
using FIDO.Nexmo;
using Flurl;
using Flurl.Http;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.Commands
{
  public class Fetch : Command
  {
    private const string url = "https://ipinfo.io/";
    private static readonly Regex regex = new Regex("^!fetch (?<message>[0-9.:A-F-a-f]*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    public Fetch(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
    }

    protected override Regex Regex => regex;

    protected override ActionMode Mode => ActionMode.OnlyAdmins;

    protected override void OnMatch(IrcMessageEventArgs ircMessage, string sender, string nick, string host, string filter, string message, string target)
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

      foreach (var ircMessageTarget in ircMessage.Targets)
      {
        ReportToIrc(result.ToString(), GetResponseChannel(ircMessage.Source.Name, ircMessageTarget.Name));
      }
    }

    // ReSharper disable once ClassNeverInstantiated.Local
    private class IpFetchResult
    {
      public override string ToString()
      {
        var location = string.Join(", ", new[] { City, Region, CountryCodeToFlag(Country) }.Where(x => !string.IsNullOrWhiteSpace(x)));
        return $"IP Information {Ip}: {location} ISP: {Org}";
      }

      private static string CountryCodeToFlag(string countryCode)
      {
        return string.Join("", Encoding.UTF8.GetBytes(countryCode.ToUpper()).Select(charCode => char.ConvertFromUtf32(charCode + 127397)));
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