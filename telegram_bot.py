import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from price_calculator import GoldPriceCalculator
from typing import List, Dict
from datetime import datetime
from html import escape


class TelegramAlertBot:
    def __init__(self):
        self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        self.price_calculator = GoldPriceCalculator()

    async def send_alert(self, product: Dict):
        """Send alert for a single product"""
        try:
            message = self._format_product_message(product)

            # Keep callback_data short (Telegram limit is strict)
            short_title = (product.get("title") or "")[:20]
            short_source = (product.get("source") or "")[:10]
            callback_key = f"details_{short_source}_{short_title}".replace(" ", "_")

            keyboard = [
                [InlineKeyboardButton("🛒 View Product", url=product.get("url", ""))],
                [InlineKeyboardButton("📊 Price Details", callback_data=callback_key)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # If sending photo: caption has a smaller limit than normal messages.
            # Keep it safe by trimming caption.
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
                    # Fall through to text message

            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=False
            )

        except Exception as e:
            print(f"Error sending Telegram alert: {e}")

    def _fmt_money(self, value) -> str:
        try:
            return f"₹{float(value):,.2f}"
        except Exception:
            return "₹0.00"

    def _safe(self, x) -> str:
        """HTML escape for Telegram HTML parse_mode."""
        return escape(str(x)) if x is not None else ""

    def _format_product_message(self, product: Dict) -> str:
        """Format product information for Telegram message (includes payment discount fields)."""

        discount_percent = float(product.get("discount_percent") or 0)

        # Emoji based on discount
        if discount_percent > 15:
            discount_emoji = "🔥🔥"
        elif discount_percent > 10:
            discount_emoji = "🔥"
        elif discount_percent > 5:
            discount_emoji = "💰"
        else:
            discount_emoji = "💎"

        # Product type emoji
        is_jewellery = bool(product.get("is_jewellery"))
        type_emoji = "💍" if is_jewellery else "🪙"

        # Core pricing fields
        selling_price = float(product.get("selling_price") or 0)
        expected_price = float(product.get("expected_price") or 0)

        # Payment discount fields (may not exist for old runs)
        pay_now_price = product.get("pay_now_price", selling_price)
        effective_price = product.get("effective_price", selling_price)
        payment_discount_value = product.get("payment_discount_value", 0)
        payment_discount_rules = product.get("payment_discount_rules", "NONE")
        best_payment_mode = product.get("best_payment_mode", "NONE")

        # price per gram – prefer effective_price if available
        price_per_gram = product.get("price_per_gram", None)
        if price_per_gram is None:
            try:
                w = float(product.get("weight_grams") or 0)
                price_per_gram = (float(effective_price) / w) if w > 0 else 0
            except Exception:
                price_per_gram = 0

        # Optional components
        making_charges_percent = float(product.get("making_charges_percent") or 0)
        gst_percent = float(product.get("gst_percent") or 0)
        spot_price = float(product.get("spot_price") or 0)

        # Timestamp formatting
        found_at = ""
        try:
            ts = product.get("timestamp")
            if ts:
                found_at = datetime.fromisoformat(ts).strftime("%I:%M %p")
        except Exception:
            found_at = ""

        # Build message (HTML parse_mode supported by Telegram) [1](https://regexr.com/)[2](https://www.geeksforgeeks.org/python/python-regex/)
        title = product.get("title") or ""
        title_short = title[:80] + ("..." if len(title) > 80 else "")
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
            f"{('<b>⏰ Found at:</b> ' + found_at) if found_at else ''}"
        )
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

    async def send_status_update(self, total_products: int, good_deals: int, scraping_time: float):
        """Send scraping status update"""
        status = (
            "🔄 <b>Scraping Complete</b>\n\n"
            "✅ Successfully scanned:\n"
            "   • Myntra - Gold products\n"
            "   • AJIO - Gold jewellery & coins\n\n"
            f"📊 <b>Results:</b>\n"
            f"   ├ Total products found: {total_products}\n"
            f"   ├ Good deals found: {good_deals}\n"
            f"   └ Scraping time: {scraping_time:.1f}s\n\n"
            "⏰ <b>Next scan:</b> Scheduled\n"
            "📈 <b>Live gold price:</b> Updated with cache\n\n"
            "<i>System running normally. Alerts sent for all good deals.</i>"
        )

        await self.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=status,
            parse_mode="HTML"
        )
``
