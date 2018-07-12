using System.Collections.Concurrent;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class ChannelFloodProtection
  {
    private readonly ConcurrentDictionary<string, FloodProtection> users = new ConcurrentDictionary<string, FloodProtection>();
    private readonly int rate;
    private readonly int per;

    public ChannelFloodProtection(int rate, int per)
    {
      this.rate = rate;
      this.per = per;
    }

    public bool ExceedsFlood(string user)
    {
      var floodProtection = users.GetOrAdd(user, u => new FloodProtection(rate, per));
      return floodProtection.ExceedsFlood();
    }
  }
}