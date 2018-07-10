using System.Collections.Concurrent;
using System.Linq;
using FIDO.Extensions;

namespace FIDO.FloodProtections
{
  public class FloodProtector
  {
    private readonly ConcurrentDictionary<string, ChannelFloodProtection> channels = new ConcurrentDictionary<string, ChannelFloodProtection>();

    private readonly IrcLayer irc;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;

    public FloodProtector(IrcLayer irc, int rate, int per, int muteDuration)
    {
      this.irc = irc;
      this.rate = rate;
      this.per = per;
      this.muteDuration = muteDuration;
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