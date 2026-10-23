"""
Synthetic PDF Generator for Automated Testing and Development Fixtures.
NOTE: These are clearly labeled synthetic test documents for validating the
pipeline and NOT real CT-200 manufacturer documents.
"""
import io
import pymupdf


def create_synthetic_pdf_v1() -> bytes:
    """Generate synthetic medical device manual PDF version 1."""
    doc = pymupdf.open()

    # --- Page 1: Overview & Power Specifications ---
    page1 = doc.new_page(width=595, height=842)  # Standard A4
    page1.insert_text(
        (50, 60),
        "CT-200 SYNTHETIC TEST MANUAL (DEVELOPMENT FIXTURE)",
        fontsize=16,
        color=(0, 0, 0)
    )
    page1.insert_text(
        (50, 85),
        "[DEVELOPMENT FIXTURE - SYNTHETIC CONTENT FOR TEST VERIFICATION ONLY]",
        fontsize=9,
        color=(0.5, 0.5, 0.5)
    )

    page1.insert_text(
        (50, 120),
        "1. System Overview",
        fontsize=14,
        color=(0, 0, 0)
    )
    page1.insert_text(
        (50, 145),
        "The CT-200 computed tomography platform is a simulated multi-slice imaging system.\n"
        "All operators must verify standard operating environment conditions before scanning.",
        fontsize=10
    )

    # Insert a Table on Page 1
    page1.insert_text((50, 200), "1.1 Operating Specifications", fontsize=12)
    page1.insert_text(
        (50, 225),
        "Parameter | Specification | Tolerance\n"
        "Input Voltage | 240 VAC | +/- 5%\n"
        "Frequency | 50/60 Hz | +/- 1 Hz\n"
        "Operating Temperature | 18 - 24 deg C | +/- 2 deg C",
        fontsize=9
    )

    # --- Page 2: Safety Requirements (v1 baseline) ---
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text(
        (50, 60),
        "2. Radiation Safety and Interlocks",
        fontsize=14
    )

    page2.insert_text(
        (50, 95),
        "2.1 Maximum Tube Voltage and Current",
        fontsize=12
    )
    page2.insert_text(
        (50, 120),
        "The high voltage generator shall not exceed a maximum tube voltage of 120 kV.\n"
        "The maximum continuous anode current limit is strictly calibrated to 500 mA.\n"
        "Exceeding these limits triggers an automatic generator cut-off.",
        fontsize=10
    )

    page2.insert_text(
        (50, 180),
        "2.2 Emergency Stop Interlock Protocol",
        fontsize=12
    )
    page2.insert_text(
        (50, 205),
        "The gantry emergency stop push-buttons must disconnect high voltage power\n"
        "to the X-ray tube assembly within 20 milliseconds of activation.\n"
        "A hardware interlock test must be performed prior to daily patient imaging.",
        fontsize=10
    )

    # Bullet list
    page2.insert_text(
        (50, 280),
        "• Check gantry rotation clearance\n"
        "• Test operator console emergency stop switch\n"
        "• Verify audio-visual exposure indicator lamps",
        fontsize=10
    )

    # --- Page 3: Duplicate Heading Test Chapters ---
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text((50, 60), "3. Hardware Subsystems", fontsize=14)
    page3.insert_text((50, 90), "Warnings and Precautions", fontsize=12)
    page3.insert_text(
        (50, 115),
        "Ensure patient table locking pins are engaged before gantry tilt motion.",
        fontsize=10
    )

    page3.insert_text((50, 170), "4. Software Subsystems", fontsize=14)
    page3.insert_text((50, 200), "Warnings and Precautions", fontsize=12)  # Duplicate heading
    page3.insert_text(
        (50, 225),
        "Do not terminate reconstruction workstation background process during raw data transfer.",
        fontsize=10
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_synthetic_pdf_v2() -> bytes:
    """
    Generate synthetic medical device manual PDF version 2.
    Differences from v1:
    - 2.1: Tube voltage increased from 120 kV to 140 kV (MODIFIED)
    - 2.2: Emergency stop latency tightened from 20 ms to 15 ms (MODIFIED)
    - 2.3: Added pediatric dose protocol (ADDED)
    - Section 3: Removed hardware warnings (DELETED)
    """
    doc = pymupdf.open()

    # --- Page 1: Overview (UNCHANGED) ---
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text(
        (50, 60),
        "CT-200 SYNTHETIC TEST MANUAL (DEVELOPMENT FIXTURE)",
        fontsize=16
    )
    page1.insert_text(
        (50, 85),
        "[DEVELOPMENT FIXTURE - SYNTHETIC CONTENT FOR TEST VERIFICATION ONLY - VERSION 2]",
        fontsize=9,
        color=(0.5, 0.5, 0.5)
    )

    page1.insert_text((50, 120), "1. System Overview", fontsize=14)
    page1.insert_text(
        (50, 145),
        "The CT-200 computed tomography platform is a simulated multi-slice imaging system.\n"
        "All operators must verify standard operating environment conditions before scanning.",
        fontsize=10
    )

    page1.insert_text((50, 200), "1.1 Operating Specifications", fontsize=12)
    page1.insert_text(
        (50, 225),
        "Parameter | Specification | Tolerance\n"
        "Input Voltage | 240 VAC | +/- 5%\n"
        "Frequency | 50/60 Hz | +/- 1 Hz\n"
        "Operating Temperature | 18 - 24 deg C | +/- 2 deg C",
        fontsize=9
    )

    # --- Page 2: Safety Requirements (MODIFIED + ADDED) ---
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 60), "2. Radiation Safety and Interlocks", fontsize=14)

    # MODIFIED: 140 kV instead of 120 kV
    page2.insert_text((50, 95), "2.1 Maximum Tube Voltage and Current", fontsize=12)
    page2.insert_text(
        (50, 120),
        "The high voltage generator shall not exceed a maximum tube voltage of 140 kV.\n"
        "The maximum continuous anode current limit is strictly calibrated to 500 mA.\n"
        "Exceeding these limits triggers an automatic generator cut-off.",
        fontsize=10
    )

    # MODIFIED: 15 ms instead of 20 ms
    page2.insert_text((50, 180), "2.2 Emergency Stop Interlock Protocol", fontsize=12)
    page2.insert_text(
        (50, 205),
        "The gantry emergency stop push-buttons must disconnect high voltage power\n"
        "to the X-ray tube assembly within 15 milliseconds of activation.\n"
        "A hardware interlock test must be performed prior to daily patient imaging.",
        fontsize=10
    )

    # ADDED Section 2.3
    page2.insert_text((50, 265), "2.3 Pediatric Dose Modulation Protocol", fontsize=12)
    page2.insert_text(
        (50, 290),
        "When pediatric scan protocol is selected, tube current modulation must reduce\n"
        "exposure index by at least 40% based on patient water-equivalent diameter.",
        fontsize=10
    )

    # --- Page 3: Software Subsystems (Section 3 hardware removed -> DELETED) ---
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text((50, 60), "4. Software Subsystems", fontsize=14)
    page3.insert_text((50, 90), "Warnings and Precautions", fontsize=12)
    page3.insert_text(
        (50, 115),
        "Do not terminate reconstruction workstation background process during raw data transfer.",
        fontsize=10
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
