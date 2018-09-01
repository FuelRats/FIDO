using System;
using System.Collections.Concurrent;
using System.Linq;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class FloodProtector : ChannelAction
  {
    private readonly ConcurrentDictionary<string, ChannelFloodProtection> channels = new ConcurrentDictionary<string, ChannelFloodProtection>();
    private readonly ConcurrentDictionary<string, ChannelMute> mutes = new ConcurrentDictionary<string, ChannelMute>();

    private readonly IrcLayer irc;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;

    public FloodProtector(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      if (Instance != null) { throw new Exception("Can only instantiate one FloodProtector"); }

      Instance = this;

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
      irc.Connected += IrcOnConnected;
      irc.Disconnected += IrcOnDisconnected;
    }

    public static FloodProtector Instance { get; private set; }

    protected override ActionMode Mode => ActionMode.OnlyUsers;

    public void MuteUser(IrcChannelUser ircChannelUser)
    {
      var mute = new ChannelMute(ircChannelUser);
      if (mutes.TryAdd(GetKey(ircChannelUser.Channel, ircChannelUser.User), mute))
      {
        mute.Mute(muteDuration);
        ReportToIrc($"MUTED {ircChannelUser.User.NickName} ({ircChannelUser.User.HostName}) has been muted for flooding in {ircChannelUser.Channel.Name}");
        irc.Client.LocalUser.SendMessage(ircChannelUser.User, $"You have been automatically muted in {ircChannelUser.Channel.Name} for {muteDuration / 1000 / 60} minutes due to too many messages in a short period of time.");
      }
    }

    public void UnmuteUser(IrcChannelUser ircChannelUser)
    {
      if (mutes.TryRemove(GetKey(ircChannelUser.Channel, ircChannelUser.User), out var mute))
      {
        mute.Unmute();
        irc.Client.LocalUser.SendMessage(ircChannelUser.User, $"You have been unmuted in {ircChannelUser.Channel.Name}.");
      }
    }

    protected override bool OnExecute(IrcMessageEventArgs ircMessage)
    {
      var user = ircMessage.Source.Name;
      foreach (var ircMessageTarget in ircMessage.Targets)
      {
        var channel = ircMessageTarget.Name;
        var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
        var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
        var channelFloodProtection = channels.GetOrAdd(channel, c => new ChannelFloodProtection(rate, per));
        if (channelFloodProtection.ExceedsFlood(user))
        {
          MuteUser(ircChannelUser);
        }
      }

      return false;
    }

    private void IrcOnDisconnected(object sender, EventArgs e)
    {
      foreach (var clientChannel in irc.Client.Channels)
      {
        clientChannel.UserJoined -= ChannelOnUserJoined;
      }

      irc.Client.LocalUser.JoinedChannel -= LocalUserOnJoinedChannel;
    }

    private void IrcOnConnected(object sender, EventArgs e)
    {
      irc.Client.LocalUser.JoinedChannel += LocalUserOnJoinedChannel;
    }

    private void LocalUserOnJoinedChannel(object sender, IrcChannelEventArgs e)
    {
      e.Channel.UserJoined += ChannelOnUserJoined;
    }

    private void ChannelOnUserJoined(object sender, IrcChannelUserEventArgs e)
    {
      var ircChannelUser = e.ChannelUser;
      if (mutes.ContainsKey(GetKey(ircChannelUser.Channel, ircChannelUser.User)))
      {
        ircChannelUser.DeVoice();
      }
    }

    private static string GetKey(IrcChannel channel, IrcUser user)
    {
      return $"{channel.Name}_{user.HostName}";
    }
  }
}