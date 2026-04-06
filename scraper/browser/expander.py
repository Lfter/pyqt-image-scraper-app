class PageExpander:
    MAX_AUTO_LOAD_ROUNDS = 24
    STABLE_ROUNDS_TO_STOP = 3
    SCROLL_PULSES_PER_ROUND = 4
    SCROLL_PULSE_SETTLE_MS = 250
    POST_ACTION_SETTLE_MS = 700

    def expand(
        self,
        page,
        get_loaded_counts,
        wait_for_network,
        scroll_action=None,
        click_action=None,
    ):
        if page is None:
            return

        scroll_action = scroll_action or (lambda: self.scroll_loading_surfaces(page))
        click_action = click_action or (lambda: self.click_load_more_control(page))
        stable_rounds = 0
        last_counts = get_loaded_counts()

        for _ in range(self.MAX_AUTO_LOAD_ROUNDS):
            moved = scroll_action()
            clicked = click_action()

            if moved or clicked:
                wait_for_network()
                page.wait_for_timeout(self.POST_ACTION_SETTLE_MS)
                wait_for_network()

            current_counts = get_loaded_counts()
            if current_counts != last_counts:
                last_counts = current_counts
                stable_rounds = 0
                continue

            if moved or clicked:
                last_counts = current_counts
                stable_rounds = 0
                continue

            stable_rounds += 1
            if stable_rounds >= self.STABLE_ROUNDS_TO_STOP:
                break

            page.wait_for_timeout(self.POST_ACTION_SETTLE_MS)

    def scroll_loading_surfaces(self, page) -> bool:
        if page is None:
            return False

        moved_any = False
        for _ in range(self.SCROLL_PULSES_PER_ROUND):
            try:
                result = page.evaluate(
                    """() => {
                        const clampMax = (value) => Math.max(0, value || 0);
                        const maxWindowY = clampMax(
                            Math.max(
                                document.documentElement ? document.documentElement.scrollHeight - window.innerHeight : 0,
                                document.body ? document.body.scrollHeight - window.innerHeight : 0,
                            )
                        );
                        const beforeWindowY = window.scrollY || window.pageYOffset || 0;
                        window.scrollTo(0, maxWindowY);
                        let moved = Math.abs((window.scrollY || window.pageYOffset || 0) - beforeWindowY) > 1;

                        const scrollables = Array.from(document.querySelectorAll('*'))
                            .filter((el) => {
                                const style = window.getComputedStyle(el);
                                const overflowY = (style.overflowY || '').toLowerCase();
                                const overflow = (style.overflow || '').toLowerCase();
                                const rect = el.getBoundingClientRect();
                                const scrollable =
                                    ['auto', 'scroll', 'overlay'].includes(overflowY) ||
                                    ['auto', 'scroll', 'overlay'].includes(overflow);
                                return (
                                    scrollable &&
                                    rect.width > 0 &&
                                    rect.height > 0 &&
                                    el.clientHeight > 0 &&
                                    el.scrollHeight > el.clientHeight + 200
                                );
                            })
                            .sort((left, right) => {
                                const leftDelta = left.scrollHeight - left.clientHeight;
                                const rightDelta = right.scrollHeight - right.clientHeight;
                                return rightDelta - leftDelta;
                            })
                            .slice(0, 8);

                        for (const el of scrollables) {
                            const maxTop = clampMax(el.scrollHeight - el.clientHeight);
                            const beforeTop = el.scrollTop || 0;
                            const delta = Math.max(el.clientHeight * 1.5, 900);
                            const targetTop = Math.min(beforeTop + delta, maxTop);
                            if (Math.abs(targetTop - beforeTop) <= 1) {
                                continue;
                            }

                            el.scrollTop = targetTop;
                            el.dispatchEvent(new Event('scroll', { bubbles: true }));
                            el.dispatchEvent(new WheelEvent('wheel', { deltaY: targetTop - beforeTop, bubbles: true }));

                            if (Math.abs((el.scrollTop || 0) - beforeTop) > 1) {
                                moved = true;
                            }
                        }

                        return { moved };
                    }"""
                )
            except Exception:
                return moved_any

            moved = bool(result and result.get("moved"))
            moved_any = moved_any or moved
            if not moved:
                break
            page.wait_for_timeout(self.SCROLL_PULSE_SETTLE_MS)

        return moved_any

    def click_load_more_control(self, page) -> bool:
        if page is None:
            return False

        try:
            result = page.evaluate(
                """() => {
                    const positivePattern = /(load\\s*more|show\\s*more|view\\s*more|more\\s*(photos|images|pictures|results)?|next\\s*page|pagination\\s*next|下一页|下页|更多|加载更多|继续加载|查看更多|展开更多)/i;
                    const negativePattern = /(prev|previous|上一页|上页|login|登录|注册|download|下载|share|分享|close|关闭|cancel|取消)/i;
                    const paginationHintPattern = /(next|page|pager|pagination|gallery|album|photo|image|pic|列表|相册|图片|照片|翻页|更多)/i;

                    const isVisible = (el) => {
                        if (!el) {
                            return false;
                        }
                        if (typeof el.checkVisibility === 'function') {
                            try {
                                if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
                                    return false;
                                }
                            } catch (error) {
                                void error;
                            }
                        }
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) {
                            return false;
                        }
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && style.pointerEvents !== 'none';
                    };

                    const candidates = Array.from(
                        document.querySelectorAll('button, [role="button"], a[href], input[type="button"], input[type="submit"]')
                    )
                        .filter((el) => {
                            const ariaDisabled = (el.getAttribute('aria-disabled') || '').toLowerCase();
                            return isVisible(el) && !el.disabled && ariaDisabled !== 'true';
                        })
                        .map((el) => {
                            const textParts = [
                                el.innerText,
                                el.textContent,
                                el.value,
                                el.getAttribute('aria-label'),
                                el.getAttribute('title'),
                                el.getAttribute('class'),
                                el.getAttribute('id'),
                                el.getAttribute('href'),
                            ]
                                .filter(Boolean)
                                .join(' ')
                                .replace(/\\s+/g, ' ')
                                .trim();
                            const lowerText = textParts.toLowerCase();
                            if (!positivePattern.test(lowerText)) {
                                return null;
                            }
                            if (negativePattern.test(lowerText)) {
                                return null;
                            }

                            let score = 0;
                            if (/(load\\s*more|show\\s*more|view\\s*more|加载更多|继续加载|查看更多|展开更多)/i.test(lowerText)) {
                                score += 5;
                            }
                            if (/(next\\s*page|pagination\\s*next|下一页|下页)/i.test(lowerText)) {
                                score += 4;
                            }
                            if (/(更多|more)/i.test(lowerText)) {
                                score += 2;
                            }
                            if (paginationHintPattern.test(lowerText)) {
                                score += 1;
                            }

                            const rect = el.getBoundingClientRect();
                            return { el, score, top: rect.top, textLength: lowerText.length };
                        })
                        .filter(Boolean)
                        .sort((left, right) => {
                            if (right.score !== left.score) {
                                return right.score - left.score;
                            }
                            if (right.top !== left.top) {
                                return right.top - left.top;
                            }
                            return left.textLength - right.textLength;
                        });

                    const best = candidates[0];
                    if (!best) {
                        return false;
                    }

                    best.el.click();
                    return true;
                }"""
            )
        except Exception:
            return False

        return bool(result)
