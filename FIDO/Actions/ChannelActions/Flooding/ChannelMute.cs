using System.Timers;
using IrcDotNet;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class ChannelMute
  {
    private readonly IrcChannel channel;
    private readonly string hostName;
    private Timer unmuteTimer;

    public ChannelMute(IrcChannel channel, string hostName)
    {
      this.channel = channel;
      this.hostName = hostName;
    }

    public void Mute(int muteDuration)
    {
      channel.SetModes("+b", $"~q:*!*@{hostName}");
      unmuteTimer = new Timer(muteDuration);
      unmuteTimer.Elapsed += UnmuteTimerOnElapsed;
      unmuteTimer.Start();
    }

    public void Unmute()
    {
      unmuteTimer.Elapsed -= UnmuteTimerOnElapsed;
      unmuteTimer.Stop();
      unmuteTimer = null;
      channel.SetModes("-b", $"~q:*!*@{hostName}");
    }

    private void UnmuteTimerOnElapsed(object sender, ElapsedEventArgs e)
    {
      Unmute();
    }
  }
}