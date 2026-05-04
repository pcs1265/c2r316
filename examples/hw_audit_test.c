/*
 * hw_audit_test.c — verify that c2r316's emulator models real R316
 * hardware faithfully on the behaviors fixed during the audit.
 *
 * Build, load on a real R316 in TPT, and capture the printed output.
 * Compare against the emulator output below. Any mismatch is an emu
 * modeling bug we still need to fix.
 *
 *   Emulator output (post-audit):
 *     T1=1 T2=0 T3=1 T4=0     (sub-imm carry: add's natural carry)
 *     T5=0 T6=1               (sub-reg control: real subtract borrow)
 *     Q=99 R=64551            (the buggy 5/10 divide loop — garbage!)
 *     R16=0                   (mov r0,r0,r0 redirects D to r16)
 *     UH=51966                (mul forwards P upper half = 0xCAFE)
 *     RT=4660                 (st/ld preserves upper half = 0x1234)
 *     DW=0                    (dw 0 reads back as 0 — assembler canonicalizes)
 *
 *   Pre-audit emu (for reference) would have printed:
 *     T1=0 T2=1 T3=0 T4=1     (real-sub borrow)
 *     T5=0 T6=1               (unchanged)
 *     Q=0  R=5                (the "naive" answer — masked the HW bug)
 *     R16=48879               (= 0xBEEF, not redirected)
 *     UH=0                    (upper zeroed)
 *     RT=0                    (upper zeroed on memory round trip)
 *     DW=31                   (= 0x1F, the physically-zero sentinel) [unverified]
 *
 * Each test is documented below with what it probes.
 */

#include <stdio.h>

/* Global cell. The compiler emits `dw 0` for this in the data section,
 * making it a probe for whether TPTASM canonicalizes physically-zero
 * data declarations. See test #3 below. */
unsigned int hw_audit_zero;

int main() {

    /* ─── #1 sub-imm carry inversion ──────────────────────────────────
     * Manual lines 313-342: `sub D, P, Simm` actually encodes as
     * `add D, P, -Simm`. The carry flag is the add's natural carry,
     * which is the OPPOSITE of a true subtract's borrow.
     *
     *   Expected on HW : T1=1 T2=0 T3=1 T4=0
     *   Pre-audit emu  : T1=0 T2=1 T3=0 T4=1   (real-sub borrow)
     */
    {
        unsigned int c1, c2, c3, c4;
        /* r1=20, sub r0, r1, 10 → real HW C=1 (20 >= 10), pre-fix emu C=0 */
        asm("mov r1, 20\n"
            "sub r0, r1, 10\n"
            "mov %0, 0\n"
            "jnc ._t1_done\n"
            "mov %0, 1\n"
            "._t1_done:"
            : "=r"(c1) :: "r1");
        /* r1=5, sub r0, r1, 10 → real HW C=0 (5 < 10), pre-fix emu C=1 */
        asm("mov r1, 5\n"
            "sub r0, r1, 10\n"
            "mov %0, 0\n"
            "jnc ._t2_done\n"
            "mov %0, 1\n"
            "._t2_done:"
            : "=r"(c2) :: "r1");
        /* cmp r1, 10 with r1=20 → same as test 1 (cmp expands to sub r0) */
        asm("mov r1, 20\n"
            "cmp r1, 10\n"
            "mov %0, 0\n"
            "jnc ._t3_done\n"
            "mov %0, 1\n"
            "._t3_done:"
            : "=r"(c3) :: "r1");
        /* cmp r1, 10 with r1=5 → C=0 on HW */
        asm("mov r1, 5\n"
            "cmp r1, 10\n"
            "mov %0, 0\n"
            "jnc ._t4_done\n"
            "mov %0, 1\n"
            "._t4_done:"
            : "=r"(c4) :: "r1");
        printf("T1=%u T2=%u T3=%u T4=%u\n", c1, c2, c3, c4);
    }

    /* ─── #2 sub-reg form (control: real subtract, carry NOT inverted) ──
     *   Expected: T5=0 T6=1
     *   (sub r0, 20, 10 reg-form: borrow=0; sub r0, 5, 10 reg-form: borrow=1)
     */
    {
        unsigned int c5, c6;
        asm("mov r1, 20\n"
            "mov r2, 10\n"
            "sub r0, r1, r2\n"
            "mov %0, 0\n"
            "jnc ._t5_done\n"
            "mov %0, 1\n"
            "._t5_done:"
            : "=r"(c5) :: "r1", "r2");
        asm("mov r1, 5\n"
            "mov r2, 10\n"
            "sub r0, r1, r2\n"
            "mov %0, 0\n"
            "jnc ._t6_done\n"
            "mov %0, 1\n"
            "._t6_done:"
            : "=r"(c6) :: "r1", "r2");
        printf("T5=%u T6=%u\n", c5, c6);
    }

    /* ─── The original hello.c hang (5/10 via the buggy divide loop) ──
     * The pre-audit emu produced the "naive" result q=0 r=5 here,
     * matching what the C programmer expected. Real HW produces
     * garbage. After the audit fix, the emu also prints garbage —
     * and so should real HW.
     *
     *   Expected on HW : Q=99 R=64551   (or some other non-(0,5) garbage)
     *   Pre-audit emu  : Q=0  R=5
     */
    {
        unsigned int q_lo, r_lo;
        asm("mov r1, 5\n"        /* dividend low */
            "mov r2, 0\n"        /* dividend high */
            "mov r13, 0\n"
            "mov r14, 0\n"
            "mov r17, 32\n"
            "._dvloop:\n"
            "add r1, r1\n"
            "adc r2, r2\n"
            "adc r13, r13\n"
            "adc r14, r14\n"
            "sub r15, r13, 10\n"  /* the buggy line: imm divisor */
            "sbb r16, r14, r0\n"
            "jc ._dvskip\n"
            "mov r13, r15\n"
            "mov r14, r16\n"
            "or  r1, 1\n"
            "._dvskip:\n"
            "sub r17, 1\n"
            "jnz ._dvloop\n"
            "mov %0, r1\n"
            "mov %1, r13\n"
            : "=r"(q_lo), "=r"(r_lo)
            :: "r1", "r2", "r13", "r14", "r15", "r16", "r17");
        printf("Q=%u R=%u\n", q_lo, r_lo);
    }

    /* ─── #15 physically-zero `mov r0,r0,r0` redirects D to r16 ──
     * Manual lines 522-531: the four physically-zero mov encodings
     * have 0x20000000 set automatically by the assembler/HW, which
     * promotes the destination from r0 to r16. Confirm by seeding
     * r16 with a known value, executing the bad encoding, then
     * reading r16 back.
     *
     *   Expected on HW : R16=0 (clobbered — old r0 contents written)
     *   Pre-audit emu  : R16=48879 (= 0xBEEF, untouched)
     */
    {
        unsigned int r16_after;
        asm("mov r16, 0xBEEF\n"
            "mov r0, r0, r0\n"   /* should redirect to r16 */
            "mov %0, r16\n"
            : "=r"(r16_after) :: "r16");
        printf("R16=%u\n", r16_after);
    }

    /* ─── #27 mul forwards P's upper 16 bits ──────────────────────────
     * Manual line 48: 16 MSBs of any ALU output (incl. mul) come from
     * P's 16 MSBs. Build a register with a known upper half via exh,
     * multiply, then exh to extract the upper half of the result.
     *
     *   Expected on HW : UH=51966 (= 0xCAFE)
     *   Pre-audit emu  : UH=0
     */
    {
        unsigned int upper;
        asm("mov r2, 0xCAFE\n"
            "exh r1, r0, r2\n"   /* r1 high = r2.low = 0xCAFE */
            "mov r2, 7\n"
            "mul r3, r1, r2\n"   /* upper from r1 = 0xCAFE per manual line 48 */
            "exh r4, r3, r0\n"   /* r4 low = r3 upper */
            "mov %0, r4\n"
            : "=r"(upper) :: "r1", "r2", "r3", "r4");
        printf("UH=%u\n", upper);
    }

    /* ─── #5 st/ld preserves full 32-bit cell ─────────────────────────
     * Manual lines 21, 56-58: cells are 32-bit. Write a value with a
     * known upper half, read back, extract. Pre-audit emu masked the
     * upper half on store and load.
     *
     *   Expected on HW : RT=4660 (= 0x1234)
     *   Pre-audit emu  : RT=0
     */
    {
        unsigned int rt;
        asm("mov r2, 0x1234\n"
            "exh r1, r0, r2\n"      /* r1 high = r2.low = 0x1234 */
            "mov r2, 0x100\n"       /* address */
            "st  r1, r2\n"
            "ld  r3, r2\n"
            "exh r4, r3, r0\n"      /* r4 low = r3 upper */
            "mov %0, r4\n"
            : "=r"(rt) :: "r1", "r2", "r3", "r4");
        printf("RT=%u\n", rt);
    }

    /* ─── #3 dw 0 read-back behavior ──────────────────────────────────
     * Manual line 32 + line 531: a `dw 0` cell stores as a physically
     * zero pattern unless the assembler canonicalizes. Reading a
     * physically-zero cell yields 0x0000001F.
     *
     * If TPTASM canonicalizes (recommended) → low half reads as 0.
     * If TPTASM does NOT canonicalize → low half reads as 0x1F = 31.
     *
     * Either way, the answer reveals what the actual assembler does.
     * Tell us which value you get on HW so we know whether the emu's
     * parser-side dw canonicalization matches reality.
     */
    {
        unsigned int dw_val = hw_audit_zero;
        printf("DW=%u\n", dw_val);
    }

    return 0;
}
