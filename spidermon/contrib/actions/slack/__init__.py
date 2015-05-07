import ast
import json
from slackclient import SlackClient

from spidermon.contrib.actions.templates import ActionWithTemplates
from spidermon.exceptions import NotConfigured


class SlackMessageManager():
    sender_token = None
    sender_name = None

    def __init__(self, sender_token=None, sender_name=None, to=None):
        sender_token = sender_token or self.sender_token
        if not sender_token:
            raise NotConfigured('You must provide a slack token.')

        self.sender_name = sender_name or self.sender_name
        if not self.sender_name:
            raise NotConfigured('You must provide a slack sender name.')

        self._client = SlackClient(sender_token)
        self._users = None

    @property
    def users(self):
        if self._users is None:
            self._users = self._get_users_info()
        return self._users

    def send_message(self, to, text, parse='full', link_names=1, attachments=None, use_mention=False):
        if isinstance(to, list):
            return [self.send_message(
                to=recipient,
                text=text,
                parse=parse,
                link_names=link_names,
                attachments=attachments,
                use_mention=use_mention,
            ) for recipient in to]
        elif to.startswith('@'):
                return self._send_user_message(
                    username=to,
                    text=text,
                    parse=parse,
                    link_names=link_names,
                    attachments=attachments)
        else:
            if use_mention:
                if to.startswith('#'):
                    text = '@channel: ' + text
                else:
                    text = '@group: ' +  text
            return self._send_channel_message(
                channel=to,
                text=text,
                parse=parse,
                link_names=link_names,
                attachments=attachments,
            )

    def _get_user_id(self, username):
        name = username[1:] if username.startswith('@') else username
        user = self.users.get(name, None)
        return user['id'] if user else None

    def _get_users_info(self):
        return dict([
            (member['name'].lower(), member)
            for member in self._api_call('users.list')['members']
        ])

    def _api_call(self, method, **kwargs):
        return json.loads(self._client.api_call(method, **kwargs))

    def _get_user_channel(self, user_id):
        return self._api_call('im.open', user=user_id)['channel']['id']

    def _send_user_message(self, username, text, parse='full', link_names=1, attachments=None):
        user_id = self._get_user_id(username)
        if user_id:
            user_channel = self._get_user_channel(user_id)
            return self._send_channel_message(
                channel=user_channel,
                text=text,
                parse=parse,
                link_names=link_names,
                attachments=attachments,
            )

    def _send_channel_message(self, channel, text, parse='full', link_names=1, attachments=None):
        return self._api_call(
            'chat.postMessage',
            channel=channel,
            text=text,
            parse=parse,
            link_names=link_names,
            attachments=self._parse_attachments(attachments),
            username=self.sender_name,
            icon_url=self.users[self.sender_name]['profile']['image_48'],
        )

    def _parse_attachments(self, attachments):
        if not attachments:
            return None
        else:
            python_attachments = ast.literal_eval(attachments)
            return json.dumps(python_attachments)


class SlackMessageAction(ActionWithTemplates):
    template_paths = ['templates']
    message = None
    attachements = None
    message_template = 'slack/default/message.jinja'
    attachments_template = 'slack/default/attachments.jinja'
    recipients = None
    sender_token = None
    sender_name = None
    include_message = True
    include_attachments = True
    fake = False

    def __init__(self,
                 sender_token=None, sender_name=None,
                 recipients=None,
                 message=None, message_template=None, include_message=None,
                 attachments=None, attachments_template=None, include_attachments=None,
                 fake=None):
        super(SlackMessageAction, self).__init__()
        self.manager = SlackMessageManager(
            sender_token=sender_token or self.sender_token,
            sender_name=sender_name or self.sender_name,
        )
        self.recipients = recipients or self.recipients
        self.message = message or self.message
        self.message_template = message_template or self.message_template
        self.include_message = include_message or self.include_message
        self.attachements = attachments or self.attachements
        self.attachments_template = attachments_template or self.attachments_template
        self.include_attachments = include_attachments or self.include_attachments
        self.fake = fake or self.fake
        if not self.recipients:
            raise NotConfigured("You must provide at least one recipient for the message.")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(**cls.from_crawler_kwargs(crawler))

    @classmethod
    def from_crawler_kwargs(cls, crawler):
        return {
            'sender_token': crawler.settings.get('SPIDERMON_SLACK_SENDER_TOKEN'),
            'sender_name': crawler.settings.get('SPIDERMON_SLACK_SENDER_NAME'),
            'recipients': crawler.settings.get('SPIDERMON_SLACK_RECIPIENTS'),
            'message': crawler.settings.get('SPIDERMON_SLACK_MESSAGE'),
            'message_template': crawler.settings.get('SPIDERMON_SLACK_MESSAGE_TEMPLATE'),
            'attachments': crawler.settings.get('SPIDERMON_SLACK_ATTACHMENTS'),
            'attachments_template': crawler.settings.get('SPIDERMON_SLACK_ATTACHMENTS_TEMPLATE'),
            'include_message': crawler.settings.get('SPIDERMON_SLACK_INCLUDE_MESSAGE'),
            'include_attachments': crawler.settings.get('SPIDERMON_SLACK_INCLUDE_ATTACHMENTS'),
            'fake': crawler.settings.get('SPIDERMON_SLACK_FAKE'),
        }

    def run_action(self):
        if not self.fake:
            self.manager.send_message(
                to=self.recipients,
                text=self.get_message(),
                attachments=self.get_attachments(),
            )

    def get_message(self):
        if self.include_message:
            return self.message or self._render_template(self.message_template)
        else:
            return None

    def get_attachments(self):
        if self.include_attachments:
            return self.attachements or self._render_template(self.attachments_template)
        else:
            return None

    def _render_template(self, template):
        template = self.get_template(template)
        return template.render(self._get_template_context())

    def _get_template_context(self):
        return {
            'result': self.result,
            'data': self.data,
            'monitors_passed': self.monitors_passed,
            'monitors_failed': self.monitors_failed,
        }