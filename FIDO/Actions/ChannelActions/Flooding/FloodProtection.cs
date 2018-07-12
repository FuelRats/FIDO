using System;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class FloodProtection
  {
    private readonly int rate;
    private readonly int per;
    private DateTime firstMessageInBurst;
    private int messageCount;

    public FloodProtection(int rate, int per)
    {
      this.rate = rate;
      this.per = per;
    }

    public bool ExceedsFlood()
    {
      var now = DateTime.UtcNow;
      if (firstMessageInBurst < now.AddSeconds(-per))
      {
        firstMessageInBurst = now;
        messageCount = 0;
      }

      messageCount++;
      return messageCount > rate;
    }
  }
}