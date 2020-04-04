import nexmo
from models import SessionManager, groups, config
from modules import configmanager


def nexmo_message(target, message):
    appid = configmanager.get_config(module='nexmo', key='appid')[0]
    secret = configmanager.get_config(module='nexmo', key='secret')[0]
    client = nexmo.Client(key=appid, secret=secret)
    res = client.send_message({'from': 'FIDO', 'to': target, 'text': message})


def get_group(group):
    """
    Fetch group members
    :param group: Name of the group
    :return: A dict of nicknames and their phonenumbers, None on failure.
    """
    session = SessionManager().session
    members = []
    for row in session.query(groups.Groups).filter_by(group=group):
        members.append({"nickname": row.nickname, "number": row.number})
    return members


def add_group(mygroup, nickname, number):
    """
    Adds a member to a group
    :param group: Group name
    :param nickname: Nickname
    :param number: Phonenumber
    :return: Nothing
    """
    session = SessionManager().session
    query = session.query(groups.Groups).filter(groups.Groups.group == mygroup).all()
    print(f"Groups: {query}")
    if nickname in query:
        return
    member = groups.Groups(nickname=nickname, number=number, group=mygroup)
    session.add(member)
    session.commit()


def send_to_group(group, message):
    """
    Sends a SMS to a specified group.
    :param group: Group name
    :param message: The message to send
    :return:
    """
    print("Sending to group...")
    members = get_group(group)
    print(f"members: {members}")
    for member in members:
        nexmo_message(member['number'], message)
    return
