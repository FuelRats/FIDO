using System;
using System.Collections.Generic;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;

namespace FIDO.Actions.ChannelActions
{
  public abstract class ChannelAction : Action
  {
    private readonly IrcLayer irc;
    private readonly string killReason;

    protected ChannelAction(IrcLayer irc, NexmoClient nexmo)
      : base(irc, nexmo)
    {
      this.irc = irc;
      killReason = Environment.GetEnvironmentVariable("KillReason");
    }

    public static IEnumerable<ChannelAction> GetAll(IrcLayer irc, NexmoClient nexmo)
    {
      yield return new ZalgoProctection(irc, nexmo);
    }

    public abstract bool Execute(IrcMessageEventArgs ircMessage);

    protected void Kill(IrcUser user, string reason = null)
    {
      if (string.IsNullOrWhiteSpace(reason))
      {
        reason = killReason;
      }

      irc.Client.SendRawMessage($"KILL {user.NickName} {reason}");
    }
  }
}