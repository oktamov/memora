/** Maps the backend's error codes onto Uzbek copy the user can act on. */
import { ApiError } from '@/shared/api/client';

const MESSAGES: Record<string, string> = {
  quota_exceeded: 'Bugungi lug‘at limiti tugadi. Ertaga yana urinib ko‘ring.',
  provider_budget_exceeded: 'Tizim bugun juda band. Saqlangan so‘zlar ishlayveradi.',
  rate_limited: 'Biroz sekinroq. Bir daqiqadan keyin urinib ko‘ring.',
  provider_unavailable: 'Lug‘at hozir javob bermayapti. Birozdan so‘ng urinib ko‘ring.',
  term_not_found: 'Bu so‘z topilmadi. Imlosini tekshirib ko‘ring.',
  term_too_long: 'So‘z juda uzun. Bu ilova so‘z va qisqa iboralar uchun.',
  term_too_many_tokens: 'Bu ilova so‘z va qisqa iboralar uchun — ko‘pi bilan 4 ta so‘z.',
  term_empty: 'So‘z kiritilmadi.',
  card_duplicate: 'Bu so‘z to‘plamda allaqachon bor.',
  deck_archived: 'Arxivlangan to‘plamga qo‘shib bo‘lmaydi.',
  daily_deck_immutable: 'Kunlik to‘plam nomini o‘zgartirib bo‘lmaydi.',
  unauthorized: 'Ilovani Telegram orqali oching.',
  bot_not_configured: 'Bot hali sozlanmagan.',
};

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Nimadir noto‘g‘ri ketdi.';
}
