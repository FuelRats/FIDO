using System.Timers;
using IrcDotNet;

namespace FIDO.Actions.ChannelActions.Flooding
{
  public class ChannelMute
  {
    private readonly IrcChannel channel;
    private readonly string hostName;
    private IrcChannelUser ircChannelUser;
    private Timer unmuteTimer;
    private bool wasVoiced;

    public ChannelMute(IrcChannelUser ircChannelUser)
    {
      channel = ircChannelUser.Channel;
      this.ircChannelUser = ircChannelUser;
      hostName = ircChannelUser.User.HostName;
      channel.UserLeft += ChannelOnUserLeft;
    }

    public void Mute(int muteDuration)
    {
      wasVoiced = ircChannelUser.Modes.Contains('v');
      if (wasVoiced)
      {
        ircChannelUser.DeVoice();
      }

      channel.SetModes("+b", $"~q:*!*@{hostName}");
      unmuteTimer = new Timer(muteDuration);
      unmuteTimer.Elapsed += UnmuteTimerOnElapsed;
      unmuteTimer.Start();
    }

    public void Unmute()
    {
      if (wasVoiced)
      {
        ircChannelUser?.Voice();
      }

      unmuteTimer.Elapsed -= UnmuteTimerOnElapsed;
      unmuteTimer.Stop();
      unmuteTimer = null;
      channel.SetModes("-b", $"~q:*!*@{hostName}");
    }

    private void ChannelOnUserLeft(object sender, IrcChannelUserEventArgs e)
    {
      if (e.ChannelUser.User == ircChannelUser.User)
      {
        channel.UserLeft -= ChannelOnUserLeft;
        ircChannelUser = null;
      }
    }

    private void UnmuteTimerOnElapsed(object sender, ElapsedEventArgs e)
    {
      Unmute();
    }
  }
}