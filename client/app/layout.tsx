import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Premium production metadata
export const metadata: Metadata = {
  title: "Saurya Gur | gur-prime-3.5",
  description:
    "Interactive AI clone and digital portfolio of Saurya Gur. Explore active systems projects, research vectors, and live development streams.",
  keywords: [
    "Saurya Gur",
    "Openfolie",
    "Systems Engineer",
    "AI Safety",
    "Software Developer",
    "gur-prime",
  ],
  authors: [{ name: "Saurya Gur", url: "https://sauryagur.me" }],
  creator: "Saurya Gur",
  openGraph: {
    title: "Saurya Gur | gur-prime-3.5",
    description: "Interactive AI clone and digital portfolio of Saurya Gur.",
    url: "https://ai.sauryagur.me",
    siteName: "Saurya Gur AI",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Saurya Gur | gur-prime-3.5",
    description: "Interactive AI clone and digital portfolio of Saurya Gur.",
    creator: "@your_twitter_handle", // Update this with your handle if you want
  },
  robots: {
    index: true,
    follow: true,
  },
};

// Forces mobile devices and browsers to paint dark system bars
export const viewport: Viewport = {
  themeColor: "#000000",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      /* Hardcoding "dark" directly forces all shadcn classes to evaluate dark tokens instantly */
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
      style={{ colorScheme: "dark" }}
    >
      {/* bg-[#0A0A0B] anchors the default background color to perfectly match the chat component layout */}
      <body className="min-h-full flex flex-col bg-[#0A0A0B] text-white">
        {children}
      </body>
    </html>
  );
}
