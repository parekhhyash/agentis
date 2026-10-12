"""The connected Gmail as a helpdesk, for teams without one: recent inbox
threads waiting on a reply are the tickets, and a reply is sent in the same
thread. Gmail has no private notes or priorities."""

from email.utils import parseaddr

from integrations.google.gmail import GmailClient, GmailThread, build_raw_message, reply_recipient, reply_subject, thread_link
from integrations.helpdesk.base import Article, HelpdeskError, Ticket, TicketMessage, clip

NAME = "Gmail"
# Customer emails from the last two weeks, without newsletters and notifications.
DEFAULT_QUERY = "in:inbox -from:me newer_than:14d -category:promotions -category:social -category:updates -category:forums"


class GmailInbox:
    name = NAME

    def __init__(self, gmail: GmailClient, own_email: str, sender_name: str, query: str | None = None):
        self._gmail = gmail
        self._own = own_email.lower()
        self._sender = f"{sender_name} <{own_email}>" if sender_name else own_email
        self._query = query or DEFAULT_QUERY

    def _ticket(self, thread: GmailThread) -> Ticket:
        customer = next((m for m in reversed(thread.messages) if parseaddr(m.sender)[1].lower() != self._own), thread.messages[0])
        name, address = parseaddr(customer.sender)
        messages = [
            TicketMessage(
                author=parseaddr(m.sender)[0] or parseaddr(m.sender)[1] or "Unknown",
                from_customer=parseaddr(m.sender)[1].lower() != self._own,
                private=False,
                created_at=m.date,
                text=m.text,
            )
            for m in thread.messages
        ]
        return Ticket(
            id=thread.id,
            subject=thread.subject or "(no subject)",
            status="open",
            priority=None,
            requester=name or address or "Customer",
            requester_email=reply_recipient(thread, self._own),
            created_at=thread.messages[0].date if thread.messages else "",
            updated_at=thread.last.date if thread.messages else "",
            url=thread_link(self._own, thread.id),
            messages=clip(messages),
            awaiting_reply=bool(messages) and messages[-1].from_customer,
        )

    async def open_tickets(self, limit: int) -> list[Ticket]:
        ids = await self._gmail.search_thread_ids(self._query, max_results=min(limit * 3, 30))
        tickets: list[Ticket] = []
        for thread_id in ids:
            ticket = self._ticket(await self._gmail.get_thread(thread_id))
            if ticket.awaiting_reply:
                tickets.append(ticket)
            if len(tickets) >= limit:
                break
        return tickets

    async def ticket(self, ticket_id: str) -> Ticket:
        return self._ticket(await self._gmail.get_thread(ticket_id))

    async def articles(self, query: str, limit: int) -> list[Article]:
        return []

    async def add_note(self, ticket_id: str, body: str) -> None:
        raise HelpdeskError("Gmail has no private notes. Send it as a reply, or copy it to your team", 409)

    async def reply(self, ticket_id: str, body: str) -> None:
        # Recipient and threading come from the thread's headers, never the model.
        thread = await self._gmail.get_thread(ticket_id)
        to = reply_recipient(thread, self._own)
        if not to:
            raise HelpdeskError("Couldn't tell who to reply to in that email thread", 409)
        last = thread.last
        raw = build_raw_message(
            sender=self._sender, to=[to], subject=reply_subject(thread.subject), body=body,
            in_reply_to=last.message_id, references=last.references,
        )
        await self._gmail.send(raw, thread_id=thread.id)

    async def set_triage(self, ticket_id: str, priority: str | None, tags: list[str]) -> None:
        raise HelpdeskError("Gmail has no priorities or tags to set", 409)
