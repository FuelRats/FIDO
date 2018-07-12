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
        ApiKey = Environment.GetEnvironmentVariable("Nexmo.api_key"),
        ApiSecret = Environment.GetEnvironmentVariable("Nexmo.api_secret")
      };

      numbers = Environment.GetEnvironmentVariable("Numbers")?.Split(',').Select(x => x.Trim()).ToList();
    }

    public void SendSms(string message)
    {
      foreach (var number in numbers)
      {
        var response = SMS.Send(new SMS.SMSRequest
        {
          from = "FuelRats",
          to = number,
          text = message
        }, creds);

        foreach (var errorMessage in response.messages.Where(x => x.status != "0"))
        {
          Console.WriteLine($"Error sending sms: {errorMessage}");
        }
      }
    }
  }
}