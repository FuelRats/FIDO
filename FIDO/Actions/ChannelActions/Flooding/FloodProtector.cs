using System.Collections.Concurrent;
using System.Linq;
using System.Text.RegularExpressions;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class FloodProtector : ChannelAction
  {
    private static readonly Regex regex = new Regex(@"^!unmute (?<nick>[A-Za-z0-9_´|\[\]]+)", RegexOptions.IgnoreCase);
    private readonly ConcurrentDictionary<string, ChannelFloodProtection> channels = new ConcurrentDictionary<string, ChannelFloodProtection>();
    private readonly ConcurrentDictionary<string, ChannelMute> mutes = new ConcurrentDictionary<string, ChannelMute>();

    private readonly IrcLayer irc;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;

    public FloodProtector(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      this.irc = irc;
      if (!int.TryParse(configuration["FloodProtectionRate"], out rate))
      {
        rate = 3;
      }

      if (!int.TryParse(configuration["FloodProtectionTime"], out per))
      {
        per = 5;
      }

      if (!int.TryParse(configuration["FloodProtectionBanDuration"], out muteDuration))
      {
        muteDuration = 5;
      }

      muteDuration *= 60 * 1000; // convert minutes to milliseconds
    }

    public override bool Execute(IrcMessageEventArgs ircMessage)
    {
      var user = ircMessage.Source.Name;
      foreach (var ircMessageTarget in ircMessage.Targets)
      {
        var channel = ircMessageTarget.Name;
        var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
        var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
        if (ircChannelUser.IsModerator())
        {
          if (ircMessage.Text.StartsWith("!unmute"))
          {
            UnmuteUser(ircChannelUser.Channel, ircMessage);
          }
        }
        else
        {
          var channelFloodProtection = channels.GetOrAdd(channel, c => new ChannelFloodProtection(rate, per));
          if (channelFloodProtection.ExceedsFlood(user))
          {
            MuteUser(ircChannelUser);
          }
        }
      }

      return false;
    }

    private void MuteUser(IrcChannelUser ircChannelUser)
    {
      var mute = new ChannelMute(ircChannelUser.Channel, ircChannelUser.User.HostName);
      if (mutes.TryAdd(GetKey(ircChannelUser.Channel, ircChannelUser.User), mute))
      {
        mute.Mute(muteDuration);
        ReportToIrc($"MUTED {ircChannelUser.User.NickName} ({ircChannelUser.User.HostName}) has been muted for flooding in {ircChannelUser.Channel.Name}");
        irc.Client.LocalUser.SendMessage(ircChannelUser.User, $"You have been automatically muted in ${ircChannelUser.Channel.Name} for {muteDuration / 1000 / 60} minutes due to too many messages in a short period of time.");
      }
    }

    private static string GetKey(IrcChannel channel, IrcUser user)
    {
      return $"{channel.Name}_{user.HostName}";
    }

    private void UnmuteUser(IrcChannel channel, IrcMessageEventArgs message)
    {
      var match = regex.Match(message.Text);
      if (match.Success)
      {
        var user = irc.Client.Users.SingleOrDefault(x => x.NickName == match.Groups["nick"].Value);
        if (user != null && mutes.TryRemove(GetKey(channel, user), out var mute))
        {
          mute.Unmute();
        }
      }
    }
  }
}