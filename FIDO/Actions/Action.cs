using System;
using System.Linq;
using FIDO.Extensions;
using FIDO.Irc;
using FIDO.Nexmo;
using IrcDotNet;
using Microsoft.Extensions.Configuration;

namespace FIDO.Actions
{
  public abstract class Action
  {
    private readonly IrcLayer irc;
    private readonly NexmoClient nexmo;
    private readonly string reportChannel;

    protected Action(IrcLayer irc, NexmoClient nexmo, IConfiguration configuration)
    {
      this.irc = irc;
      this.nexmo = nexmo;

      reportChannel = configuration["OperChannel"];
      if (string.IsNullOrWhiteSpace(reportChannel))
      {
        reportChannel = "#opers";
      }
    }

    protected abstract ActionMode Mode { get; }

    public bool Execute(IrcMessageEventArgs ircMessage)
    {
      bool execute;
      switch (Mode)
      {
        case ActionMode.OnlyUsers:
          execute = !IsMessageFromModerator(ircMessage.Source.Name, ircMessage.Targets.FirstOrDefault()?.Name);
          break;
        case ActionMode.OnlyAdmins:
          execute = IsMessageFromModerator(ircMessage.Source.Name, ircMessage.Targets.FirstOrDefault()?.Name);
          break;
        case ActionMode.All:
          execute = true;
          break;
        default:
          throw new ArgumentOutOfRangeException();
      }

      return execute && OnExecute(ircMessage);
    }

    protected abstract bool OnExecute(IrcMessageEventArgs ircMessage);

    protected void ReportToIrc(string message, string channel = null)
    {
      irc.Client.LocalUser.SendMessage(channel ?? reportChannel, message);
    }

    protected void SendSms(string message)
    {
      nexmo.SendSms(message);
    }

    protected IrcUser GetUser(string name)
    {
      return irc.Client.Users.SingleOrDefault(x => x.NickName == name);
    }

    protected string GetResponseChannel(string source, string target)
    {
      return irc.Client.LocalUser.NickName == target ? source : target;
    }

    private bool IsMessageFromModerator(string user, string channel)
    {
      var ircUser = irc.Client.Users.Single(x => x.NickName == user);
      if (string.IsNullOrWhiteSpace(channel) || !channel.StartsWith("#"))
      {
        return ircUser.IsModerator();
      }

      var ircChannel = irc.Client.Channels.Single(x => x.Name == channel);
      var ircChannelUser = ircChannel.Users.Single(x => x.User.NickName == user);
      return ircChannelUser.IsModerator();
    }
  }
}