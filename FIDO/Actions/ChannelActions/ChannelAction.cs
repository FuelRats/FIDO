using System.Collections.Generic;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions.ChannelActions
{
  public abstract class ChannelAction : Action
  {
    private readonly IrcLayer irc;
    private readonly string killReason;

    protected ChannelAction(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
      : base(irc, nexmo, configuration)
    {
      this.irc = irc;
      killReason = configuration["KillReason"];
    }

    public static IEnumerable<ChannelAction> GetAll(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
    {
      yield return new HighlightCount(irc, nexmo, configuration);
      //yield return new ZalgoProctection(irc, nexmo);
    }

    public abstract bool Execute(IrcMessageEventArgs ircMessage);

    protected void Kill(IrcUser user, string reason = null)
    {
      if (user == null)
      {
        return;
      }

      if (string.IsNullOrWhiteSpace(reason))
      {
        reason = killReason;
      }

      irc.Client.SendRawMessage($"KILL {user.NickName} {reason}");
    }
  }
}