"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

const CITIES = [
  // India
  "Bangalore", "Bengaluru", "Hyderabad", "Mumbai", "Pune", "Chennai",
  "Delhi", "Noida", "Gurugram", "Kolkata", "Ahmedabad", "Jaipur",
  "Bhubaneswar", "Kochi", "Thiruvananthapuram", "Chandigarh", "Indore",
  // US
  "San Francisco", "New York", "Seattle", "Austin", "Boston",
  "Los Angeles", "Chicago", "Denver", "Portland", "Atlanta",
  "Washington DC", "Miami", "San Jose", "Palo Alto", "Mountain View",
  // Europe
  "London", "Berlin", "Amsterdam", "Paris", "Dublin", "Munich",
  "Barcelona", "Stockholm", "Zurich", "Lisbon", "Warsaw", "Prague",
  "Vienna", "Copenhagen", "Helsinki", "Milan", "Madrid", "Brussels",
  // Canada
  "Toronto", "Vancouver", "Montreal", "Ottawa",
  // Asia-Pacific
  "Singapore", "Tokyo", "Sydney", "Melbourne", "Hong Kong", "Seoul",
  "Taipei", "Jakarta", "Bangkok", "Ho Chi Minh City",
  // Middle East
  "Dubai", "Tel Aviv", "Riyadh",
  // Remote
  "Remote", "Anywhere",
];

interface CityComboboxProps {
  selected: string[];
  onChange: (cities: string[]) => void;
  placeholder?: string;
}

export function CityCombobox({
  selected,
  onChange,
  placeholder = "Type to search cities…",
}: CityComboboxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const filtered = query.trim()
    ? CITIES.filter(
        (c) =>
          c.toLowerCase().includes(query.toLowerCase()) &&
          !selected.includes(c)
      ).slice(0, 8)
    : [];

  const add = useCallback(
    (city: string) => {
      if (!selected.includes(city)) {
        onChange([...selected, city]);
      }
      setQuery("");
    },
    [selected, onChange]
  );

  const remove = (city: string) => onChange(selected.filter((c) => c !== city));

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex flex-wrap gap-1.5 rounded-xl border border-mist bg-white px-3 py-2 focus-within:border-lime/60">
        {selected.map((city) => (
          <span
            key={city}
            className="inline-flex items-center gap-1 rounded-full bg-ink/5 px-2.5 py-1 text-sm font-medium text-ink"
          >
            {city}
            <button
              type="button"
              onClick={() => remove(city)}
              className="text-stone hover:text-ink"
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) {
              e.preventDefault();
              if (filtered.length > 0) {
                add(filtered[0]);
              } else {
                add(query.trim());
              }
            }
            if (e.key === "Backspace" && !query && selected.length > 0) {
              remove(selected[selected.length - 1]);
            }
          }}
          placeholder={selected.length === 0 ? placeholder : ""}
          className="min-w-[120px] flex-1 bg-transparent text-base text-ink outline-none placeholder:text-stone/40"
        />
      </div>

      {open && filtered.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-mist bg-white py-1 shadow-lg">
          {filtered.map((city) => (
            <li key={city}>
              <button
                type="button"
                onClick={() => {
                  add(city);
                  inputRef.current?.focus();
                }}
                className="w-full px-3 py-2 text-left text-base text-ink hover:bg-sage/30"
              >
                {city}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
