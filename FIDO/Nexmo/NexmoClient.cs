using System;
using System.Collections.Generic;
using System.Linq;
using Nexmo.Api;
using Nexmo.Api.Request;

namespace FIDO.Nexmo
{
  public class NexmoClient
  {
    private readonly Credentials creds;
    private readonly IList<string> numbers;

    public NexmoClient()
    {
      creds = new Credentials
      {
        ApiKey = Environment.GetEnvironmentVariable("Nexmo.UserAgent"),
        ApiSecret = Environment.GetEnvironmentVariable("Nexmo.api_secret"),
        ApplicationId = Environment.GetEnvironmentVariable("Nexmo.Application.Id"),
        ApplicationKey = Environment.GetEnvironmentVariable("Nexmo.Application.Key")
      };

      numbers = Environment.GetEnvironmentVariable("Numbers")?.Split(',').Select(x => x.Trim()).ToList();
    }

    public void SendSms(string message)
    {
      foreach (var number in numbers)
      {
        SMS.Send(new SMS.SMSRequest
        {
          from = "FIDO",
          to = number,
          text = message
        }, creds);
      }
    }
  }
}