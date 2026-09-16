from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Channel, NotificationPreference, Template, User

USERS = [
    User(id="42", email="anushka@example.com", phone="+910000000042", push_token="tok-42"),
    User(id="7", email="optout@example.com", phone="+910000000007", push_token="tok-7"),
    User(id="fail", email="fail-invalid", phone="fail-invalid", push_token="fail-invalid"),
]

TEMPLATES = [
    Template(code="ORDER_SHIPPED", channel=Channel.inapp, subject="Shipped", body="Order {{order_id}} is on the way, {{user_name}}."),
    Template(code="ORDER_SHIPPED", channel=Channel.email, subject="Your order {{order_id}} shipped", body="Hi {{user_name}}, order {{order_id}} has shipped."),
    Template(code="ORDER_SHIPPED", channel=Channel.sms, subject="", body="Order {{order_id}} shipped."),
    Template(code="ORDER_SHIPPED", channel=Channel.push, subject="Shipped", body="Order {{order_id}} shipped."),
    Template(code="OTP", channel=Channel.sms, subject="", body="Your code is {{code}}."),
    Template(code="OTP", channel=Channel.email, subject="Your code", body="Your code is {{code}}."),
    Template(code="PROMO", channel=Channel.email, subject="{{headline}}", body="{{user_name}}, {{headline}}"),
    Template(code="PROMO", channel=Channel.inapp, subject="{{headline}}", body="{{headline}}"),
    Template(code="COMMENT", channel=Channel.inapp, subject="New comment", body="{{user_name}} commented: {{text}}"),
    Template(code="COMMENT", channel=Channel.push, subject="New comment", body="{{user_name}} commented: {{text}}"),
]


async def seed(session: AsyncSession) -> None:
    for user in USERS:
        if await session.get(User, user.id) is None:
            session.add(User(id=user.id, email=user.email, phone=user.phone, push_token=user.push_token))
    await session.flush()

    for tmpl in TEMPLATES:
        exists = await session.scalar(
            select(Template).where(Template.code == tmpl.code, Template.channel == tmpl.channel)
        )
        if exists is None:
            session.add(Template(code=tmpl.code, channel=tmpl.channel, subject=tmpl.subject, body=tmpl.body))

    optout = await session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == "7",
            NotificationPreference.category == Category.marketing,
            NotificationPreference.channel == Channel.email,
        )
    )
    if optout is None:
        session.add(
            NotificationPreference(
                user_id="7",
                category=Category.marketing,
                channel=Channel.email,
                enabled=False,
            )
        )
    await session.commit()
