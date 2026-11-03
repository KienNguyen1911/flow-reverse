import { useMemo, useState } from "react";
import type { AssetOutputItem, AssetUploadedItem } from "../../types";
import { getTimestamp } from "./format";

/** Search / sort / category state and the derived (filtered, sorted, pinned-first) lists for both asset tabs. */
export function useAssetFilters(uploaded: AssetUploadedItem[], outputs: AssetOutputItem[]) {
  // Sorting state: "newest" vs "oldest"
  const [uploadSort, setUploadSort] = useState<"newest" | "oldest">("newest");
  const [outputSort, setOutputSort] = useState<"newest" | "oldest">("newest");

  // Output tab category filter: "all" | "image" | "video"
  const [categoryFilter, setCategoryFilter] = useState<"all" | "image" | "video">("all");

  // Search queries
  const [searchUpload, setSearchUpload] = useState("");
  const [searchOutput, setSearchOutput] = useState("");

  // Process & filter Uploaded items
  const processedUploaded = useMemo(() => {
    let list = [...uploaded];

    // Search query
    if (searchUpload.trim()) {
      const q = searchUpload.toLowerCase();
      list = list.filter((item) => item.name.toLowerCase().includes(q));
    }

    // Sort by time
    list.sort((a, b) => {
      const tA = getTimestamp(a.created_ts);
      const tB = getTimestamp(b.created_ts);
      return uploadSort === "newest" ? tB - tA : tA - tB;
    });

    // Pinned priority: pinned items always float to the top
    const pinnedList: AssetUploadedItem[] = [];
    const regularList: AssetUploadedItem[] = [];
    for (const item of list) {
      if (item.isPinned) {
        pinnedList.push(item);
      } else {
        regularList.push(item);
      }
    }

    return {
      pinned: pinnedList,
      regular: regularList,
      all: [...pinnedList, ...regularList],
    };
  }, [uploaded, searchUpload, uploadSort]);

  // Process & filter Output items
  const processedOutputs = useMemo(() => {
    let list = [...outputs];

    // Category filter: image vs video vs all
    if (categoryFilter !== "all") {
      list = list.filter((item) => item.category === categoryFilter);
    }

    // Search query
    if (searchOutput.trim()) {
      const q = searchOutput.toLowerCase();
      list = list.filter(
        (item) =>
          item.name.toLowerCase().includes(q) ||
          (item.prompt && item.prompt.toLowerCase().includes(q)),
      );
    }

    // Sort by time
    list.sort((a, b) => {
      const tA = getTimestamp(a.created_ts);
      const tB = getTimestamp(b.created_ts);
      return outputSort === "newest" ? tB - tA : tA - tB;
    });

    const pinnedList = list.filter((item) => item.isPinned);
    const regularList = list.filter((item) => !item.isPinned);

    return { pinned: pinnedList, regular: regularList, all: list };
  }, [outputs, categoryFilter, searchOutput, outputSort]);

  const pinnedCount = useMemo(
    () =>
      uploaded.filter((i) => i.isPinned).length + outputs.filter((i) => i.isPinned).length,
    [uploaded, outputs],
  );

  // Category counts for outputs
  const outputCounts = useMemo(() => {
    let imgCount = 0;
    let vidCount = 0;
    for (const item of outputs) {
      if (item.category === "video") vidCount++;
      else imgCount++;
    }
    return { all: outputs.length, image: imgCount, video: vidCount };
  }, [outputs]);

  return {
    uploadSort,
    setUploadSort,
    outputSort,
    setOutputSort,
    categoryFilter,
    setCategoryFilter,
    searchUpload,
    setSearchUpload,
    searchOutput,
    setSearchOutput,
    processedUploaded,
    processedOutputs,
    pinnedCount,
    outputCounts,
  };
}

export type AssetFilters = ReturnType<typeof useAssetFilters>;
