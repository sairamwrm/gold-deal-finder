import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from price_calculator import GoldPriceCalculator
from typing import List, Dict
from datetime import datetime
from html import escape


class TelegramAlertBot:
    def __init__(self):
        self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        self.price_calculator = GoldPriceCalculator()

    def _safe(self, x) -> str:
        return escape(str(x)) if x is not None else ""

    def _fmt_money(self, value) -> str:
        try:
            return f"₹{float(value):,.2f}"
        except Exception:
            return "₹0.00"

    async def send_alert(self, product: Dict):
        """Send alert for a single product"""
        try:
            message = self._format_product_message(product)

            # Inline keyboard
            url = product.get("url", "")
            short_title = (product.get("title") or "")[:20].replace(" ", "_")
            short_source = (product.get("source") or "")[:10].replace(" ", "_")
            callback_key = f"details_{short_source}_{short_title}"

            keyboard = [
                [InlineKeyboardButton("🛒 View Product", url=url)],
                [InlineKeyboardButton("📊 Price Details", callback_data=callback_key)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send photo if available
            if product.get("image_url"):
                try:
                    caption = message
                    if len(caption) > 900:
                        caption = caption[:900] + "\n<i>(trimmed)</i>"

                    await self.bot.send_photo(
                        chat_id=TELEGRAM_CHAT_ID,
                        photo=product["image_url"],
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    return
                except Exception as e:
                    print(f"Failed to send photo: {e}")

            # Send as text
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=False
            )

        except Exception as e:
            print(f"Error sending Telegram alert: {e}")

    def _format_product_message(self, product: Dict) -> str:
        """Format product information for Telegram message including payment fields."""

        discount_percent = float(product.get("discount_percent") or 0)

        if discount_percent > 15:
            discount_emoji = "🔥🔥"
        elif discount_percent > 10:
            discount_emoji = "🔥"
        elif discount_percent > 5:
            discount_emoji = "💰"
        else:
            discount_emoji = "💎"

        is_jewellery = bool(product.get("is_jewellery"))
        type_emoji = "💍" if is_jewellery else "🪙"

        title = product.get("title") or ""
        title_short = title[:80] + ("..." if len(title) > 80 else "")

        selling_price = float(product.get("selling_price") or 0)
        expected_price = float(product.get("expected_price") or 0)

        # Payment fields (fallback safely if missing)
        pay_now_price = float(product.get("pay_now_price", selling_price) or selling_price)
        effective_price = float(product.get("effective_price", selling_price) or selling_price)
        payment_discount_value = float(product.get("payment_discount_value", 0) or 0)
        payment_discount_rules = product.get("payment_discount_rules", "NONE")
        best_payment_mode = product.get("best_payment_mode", "NONE")

        weight = float(product.get("weight_grams") or 0)
        price_per_gram = product.get("price_per_gram")
        if price_per_gram is None:
            price_per_gram = (effective_price / weight) if weight > 0 else 0

        making_charges_percent = float(product.get("making_charges_percent") or 0)
        gst_percent = float(product.get("gst_percent") or 0)
        spot_price = float(product.get("spot_price") or 0)

        found_at = ""
        try:
            ts = product.get("timestamp")
            if ts:
                found_at = datetime.fromisoformat(ts).strftime("%I:%M %p")
        except Exception:
            found_at = ""

        message = (
            f"{discount_emoji} <b>GOLD DEAL ALERT!</b> {discount_emoji}\n\n"
            f"{type_emoji} <b>{self._safe(product.get('source',''))} - {self._safe(product.get('brand',''))}</b>\n"
            f"📦 <b>Product:</b> {self._safe(title_short)}\n\n"
            f"<b>⚖️ Weight:</b> {self._safe(product.get('weight_grams',''))}g\n"
            f"<b>🔬 Purity:</b> {self._safe(product.get('purity',''))}\n"
            f"<b>🏷️ Type:</b> {'Jewellery' if is_jewellery else 'Coin/Bar'}\n\n"
            f"<b>💰 Listed Price:</b> {self._fmt_money(selling_price)}\n"
            f"<b>💳 Best Payment Mode:</b> {self._safe(best_payment_mode)}\n"
            f"<b>⚡ Pay-now Price:</b> {self._fmt_money(pay_now_price)}\n"
            f"<b>🎁 Effective Price:</b> {self._fmt_money(effective_price)} "
            f"<i>(benefit {self._fmt_money(payment_discount_value)})</i>\n"
            f"<b>📈 Expected Value:</b> {self._fmt_money(expected_price)}\n"
            f"<b>💎 Price per gram:</b> {self._fmt_money(price_per_gram)}\n\n"
            f"<b>📊 Making Charges:</b> {making_charges_percent:.1f}%\n"
            f"<b>🧾 GST:</b> {gst_percent:.1f}%\n\n"
            f"<code>🎯 DISCOUNT: {discount_percent:.1f}%</code>\n\n"
            f"<b>🏪 Market Spot Price:</b> ₹{spot_price:,.2f}/g\n"
            f"<b>🏷 Payment Rules:</b> <i>{self._safe(payment_discount_rules)}</i>\n"
        )

        if found_at:
            message += f"\n<b>⏰ Found at:</b> {found_at}"

        return message

    async def send_bulk_alerts(self, products: List[Dict]):
        """Send alerts for multiple products"""
        if not products:
            await self.send_no_deals_message()
            return

        products.sort(key=lambda x: float(x.get("discount_percent") or 0), reverse=True)

        await self.send_price_summary()

        for product in products[:5]:
            await self.send_alert(product)

        if len(products) > 5:
            await self.send_deals_summary(products)

    async def send_price_summary(self):
        """Send current gold price summary"""
        try:
            summary = self.price_calculator.get_price_summary()
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=summary,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error sending price summary: {e}")

    async def send_no_deals_message(self):
        """Send message when no deals found"""
        message = (
            "📭 <b>No Gold Deals Found</b>\n\n"
            "No significant discounts found in the current scan.\n"
            "Will check again in the next cycle.\n\n"
            "💡 <i>Tip: Check back during sale events for better deals!</i>"
        )
        await self.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="HTML"
        )

    async def send_deals_summary(self, products: List[Dict]):
        """Send summary of all deals"""
        top_deals = products[:5]
        other_deals = products[5:]

        summary = "📋 <b>Deals Summary</b>\n\n"
        summary += f"<b>Top {len(top_deals)} Deals:</b>\n"

        for i, product in enumerate(top_deals, 1):
            summary += (
                f"{i}. {escape(product.get('source',''))}: "
                f"{float(product.get('discount_percent') or 0):.1f}% off "
                f"({product.get('weight_grams','')}g {escape(product.get('purity',''))})\n"
            )

        if other_deals:
            summary += f"\n<b>Plus {len(other_deals)} more deals available!</b>"

        summary += f"\n\n<i>Total deals found: {len(products)}</i>"

        await self.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=summary,
            parse_mode="HTML"
        )
