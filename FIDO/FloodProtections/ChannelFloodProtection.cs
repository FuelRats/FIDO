using System.Collections.Concurrent;

namespace FIDO.FloodProtections
{
  public class ChannelFloodProtection
  {
    private readonly ConcurrentDictionary<string, FloodProtection> users = new ConcurrentDictionary<string, FloodProtection>();
    private readonly IrcLayer irc;
    private readonly string channel;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;

    public ChannelFloodProtection(IrcLayer irc, string channel, int rate, int per, int muteDuration)
    {
      this.irc = irc;
      this.channel = channel;
      this.rate = rate;
      this.per = per;
      this.muteDuration = muteDuration;
    }

    public void Check(string user)
    {
      var floodProtection = users.GetOrAdd(user, u => new FloodProtection(irc, channel, user, rate, per, muteDuration));
      floodProtection.Check();
    }
  }
}