using System;
using System.Collections.Generic;
using System.Linq;
using FIDO.Extensions;
using Microsoft.Extensions.Configuration;
using Nexmo.Api;
using Nexmo.Api.Request;

namespace FIDO.Nexmo
{
  public class NexmoClient
  {
    private readonly Credentials creds;
    private readonly IList<string> numbers = new List<string>();

    public NexmoClient(IConfiguration configuration)
    {
      creds = new Credentials
      {
        ApiKey = configuration["Nexmo.api_key"],
        ApiSecret = configuration["Nexmo.api_secret"]
      };

      numbers.AddRange(configuration["Numbers"].Split(',').Select(x => x.Trim()));
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