using System;
using System.Linq;
using System.Timers;
using FIDO.Irc;

namespace FIDO.FloodProtections
{
  public class FloodProtection
  {
    private readonly IrcLayer irc;
    private readonly string channel;
    private readonly string user;
    private readonly int rate;
    private readonly int per;
    private readonly int muteDuration;
    private DateTime firstMessageInBurst;
    private int messageCount;

    public FloodProtection(IrcLayer irc, string channel, string user, int rate, int per, int muteDuration)
    {
      this.irc = irc;
      this.channel = channel;
      this.user = user;
      this.rate = rate;
      this.per = per;
      this.muteDuration = muteDuration;
    }

    public void Check()
    {
      var now = DateTime.UtcNow;
      if (firstMessageInBurst < now.AddSeconds(-per))
      {
        firstMessageInBurst = now;
        messageCount = 0;
      }

      messageCount++;
      var check = messageCount > rate;
      if (check)
      {
        Console.WriteLine($"FLOODING: user {user} in channel {channel}");

        var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
        var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
        ircChannel.SetModes("+b", $"~q:*!*@{ircChannelUser.User.HostName}");
        var unmuteTimer = new Timer(muteDuration /* 60*/ * 1000);
        unmuteTimer.Elapsed += UnmuteTimerOnElapsed;
        unmuteTimer.Start();
      }
    }

    private void UnmuteTimerOnElapsed(object sender, ElapsedEventArgs e)
    {
      var timer = (Timer) sender;
      timer.Elapsed -= UnmuteTimerOnElapsed;

      Console.WriteLine($"UNMUTING: user {user} in channel {channel}");

      var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
      var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
      ircChannel.SetModes("-b", $"~q:*!*@{ircChannelUser.User.HostName}");
    }
  }
}