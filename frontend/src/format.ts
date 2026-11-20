// Format a decimal string as Indian rupees: "138948.30" -> "₹1,38,948.30".
//
// Done on the string, not via Number(), so a money value never passes through
// a float, even for display. Indian grouping: the last three digits, then
// groups of two (1,25,400 not 125,400).

export function formatINR(amount: string | null): string {
  if (amount === null) return "—";

  const negative = amount.startsWith("-");
  const [intPart, frac = ""] = (negative ? amount.slice(1) : amount).split(".");

  let grouped = intPart;
  if (intPart.length > 3) {
    const head = intPart.slice(0, -3);
    const tail = intPart.slice(-3);
    grouped = head.replace(/\B(?=(\d{2})+$)/g, ",") + "," + tail;
  }

  const paise = (frac + "00").slice(0, 2);
  return `${negative ? "-" : ""}₹${grouped}.${paise}`;
}
