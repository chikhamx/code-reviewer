from code_review_agent.models.review import Finding


class ResultMerger:
    """Merges, deduplicates, and prioritizes review findings from multiple sources."""

    SEVERITY_ORDER = {
        "critical": 0, "error": 1, "warning": 2, "info": 3, "suggestion": 4,
    }

    def merge(
        self,
        *finding_lists: list[Finding],
        dedup_window: int = 3,
    ) -> list[Finding]:
        """Merge multiple finding lists, deduplicating nearby findings."""
        all_findings: list[Finding] = []
        for flist in finding_lists:
            all_findings.extend(flist)

        all_findings = self._deduplicate(all_findings, dedup_window)
        all_findings.sort(key=self._sort_key)
        return all_findings

    def _deduplicate(self, findings: list[Finding], window: int) -> list[Finding]:
        """Remove findings that are within `window` lines of each other on the same file and category."""
        if not findings:
            return []

        # Group by file + category
        groups: dict[tuple, list[Finding]] = {}
        for f in findings:
            key = (f.file, f.category.value)
            groups.setdefault(key, []).append(f)

        result: list[Finding] = []
        for flist in groups.values():
            flist.sort(key=lambda f: f.line or 0)
            kept = [flist[0]]
            for f in flist[1:]:
                prev = kept[-1]
                line_diff = abs((f.line or 0) - (prev.line or 0))
                if line_diff > window or f.title != prev.title:
                    kept.append(f)
            result.extend(kept)

        return result

    def _sort_key(self, f: Finding) -> tuple:
        return (
            self.SEVERITY_ORDER.get(f.severity.value, 5),
            f.file,
            f.line or 0,
        )
