using System.Collections.Concurrent;
using System.Linq;
using FIDO.Extensions;
using FIDO.Irc;
using Microsoft.Extensions.Configuration;

namespace FIDO.FloodProtections
{
  public class FloodProtector
  {
    private readonly ConcurrentDictionary<string, ChannelFloodProtection> channels = new ConcurrentDictionary<string, ChannelFloodProtection>();

    private readonly IrcLayer irc;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;

    public FloodProtector(IrcLayer irc, IConfiguration configuration)
    {
      this.irc = irc;
      if (!int.TryParse(configuration["FloodProtectionRate"], out rate))
      {
        rate = 3;
      }

      if (!int.TryParse(configuration["FloodProtectionTime"], out per))
      {
        per = 3;
      }

      if (!int.TryParse(configuration["FloodProtectionDuration"], out muteDuration))
      {
        muteDuration = 3;
      }
    }

    public void Check(string channel, string user)
    {
      var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
      var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
      if (ircChannelUser.IsModerator())
      {
        return;
      }

      var channelFloodProtection = channels.GetOrAdd(channel, c => new ChannelFloodProtection(irc, channel, rate, per, muteDuration));
      channelFloodProtection.Check(user);
    }
  }
}