"""Curated local-lead niche terminology used by search planning and local AI.

The catalog is prompt/retrieval memory, not model weights.  Each entry stays editable
through the existing niche-pack UI after it is seeded into SQLite.
"""

from __future__ import annotations

import re


_ROWS = """
roofing contractors|roofer|roof repair|roof replacement
plumbers|plumber|plumbing contractor|emergency plumbing
electricians|electrician|electrical contractor|electrical repair
HVAC contractors|HVAC company|air conditioning contractor|heating contractor
general contractors|general contractor|construction company|building contractor
remodeling contractors|home remodeler|renovation contractor|home renovation
kitchen remodeling|kitchen remodeler|kitchen renovation|cabinet remodeling
bathroom remodeling|bathroom remodeler|bath renovation|shower remodeling
basement remodeling|basement finishing|basement contractor|lower level renovation
home builders|custom home builder|residential builder|new home construction
architects|architecture firm|residential architect|commercial architect
interior designers|interior design firm|home interior designer|commercial interior design
painters|painting contractor|house painter|commercial painting
drywall contractors|drywall installer|sheetrock repair|drywall repair
flooring installers|flooring contractor|floor installation|hardwood installer
tile contractors|tile installer|tile installation|ceramic tile contractor
concrete contractors|concrete company|concrete repair|concrete installer
masonry contractors|masonry company|brick contractor|stone masonry
foundation repair|foundation contractor|structural foundation repair|foundation stabilization
waterproofing contractors|basement waterproofing|waterproofing company|moisture control
insulation contractors|insulation installer|attic insulation|spray foam contractor
siding contractors|siding installer|vinyl siding company|exterior siding
window installers|window replacement|window contractor|replacement windows
door installers|door replacement|entry door contractor|commercial door service
garage door repair|garage door company|overhead door service|garage door installer
fence contractors|fence company|fence installer|residential fencing
deck builders|deck contractor|deck construction|deck repair
patio builders|patio contractor|outdoor living contractor|paver patio installer
gutter installers|gutter company|gutter repair|seamless gutters
chimney sweeps|chimney cleaning|chimney service|chimney inspection
fireplace services|fireplace repair|fireplace installer|gas fireplace service
solar installers|solar company|solar panel contractor|residential solar
generator installers|generator service|standby generator contractor|backup generator
pool builders|swimming pool contractor|pool construction|custom pool builder
pool cleaning|pool service|swimming pool maintenance|pool repair
hot tub services|spa repair|hot tub repair|hot tub maintenance
landscapers|landscaping company|landscape contractor|landscape maintenance
lawn care|lawn service|grass cutting|yard maintenance
tree services|tree removal|tree trimming|stump grinding
arborists|certified arborist|tree health service|tree care specialist
irrigation contractors|sprinkler repair|irrigation installer|lawn sprinkler service
garden designers|garden design|landscape designer|planting design
pest control|exterminator|pest management|termite control
wildlife removal|animal removal|nuisance wildlife control|critter removal
junk removal|haul away service|debris removal|rubbish removal
dumpster rental|roll off dumpster|waste container rental|construction dumpster
moving companies|movers|moving service|residential moving
self storage|storage facility|storage units|mini storage
house cleaning|home cleaning service|residential cleaner|maid service
commercial cleaning|office cleaning|business cleaning service|facility cleaning
janitorial services|janitorial company|custodial service|building maintenance cleaning
carpet cleaning|carpet cleaner|rug cleaning|commercial carpet cleaning
upholstery cleaning|furniture cleaning|sofa cleaning|fabric cleaning service
pressure washing|power washing|exterior cleaning|soft washing
window cleaning|window washer|commercial window cleaning|glass cleaning service
hood cleaning|kitchen exhaust cleaning|restaurant hood cleaning|commercial hood degreasing
air duct cleaning|duct cleaner|HVAC duct cleaning|vent cleaning
dryer vent cleaning|dryer duct cleaning|dryer vent service|lint removal service
mold remediation|mold removal|mold inspection|fungal remediation
water damage restoration|flood cleanup|water restoration|emergency water removal
fire damage restoration|smoke damage cleanup|fire restoration|odor remediation
asbestos removal|asbestos abatement|hazardous material abatement|asbestos contractor
biohazard cleanup|crime scene cleanup|trauma cleanup|hazardous cleanup
septic services|septic pumping|septic tank cleaning|septic repair
portable toilet rental|porta potty rental|temporary restroom rental|mobile toilet service
locksmiths|locksmith|emergency locksmith|commercial locksmith
security system installers|alarm company|security camera installer|access control installer
smart home installers|home automation installer|smart home company|automation integrator
appliance repair|appliance service|washer repair|refrigerator repair
handyman services|handyman|home repair service|property maintenance
auto repair|auto mechanic|car repair shop|automotive service
mobile mechanics|mobile mechanic|on site auto repair|traveling mechanic
auto body shops|collision repair|body shop|paint and body repair
windshield repair|auto glass repair|windshield replacement|mobile auto glass
tire shops|tire dealer|tire repair|wheel and tire service
car detailing|auto detailing|mobile detailing|vehicle detailing
car washes|car wash|automatic car wash|hand car wash
towing companies|tow truck service|vehicle towing|emergency towing
roadside assistance|roadside service|jump start service|vehicle lockout service
motorcycle repair|motorcycle mechanic|motorbike service|powersports repair
RV repair|recreational vehicle repair|mobile RV service|camper repair
boat repair|marine repair|boat mechanic|marine service
truck repair|diesel truck repair|heavy duty repair|commercial truck service
fleet maintenance|fleet repair|commercial vehicle maintenance|mobile fleet service
vehicle wrap installers|car wraps|commercial vehicle wraps|vinyl wrap shop
auto glass tinting|window tint shop|car window tinting|automotive tint
car dealerships|auto dealer|new car dealer|automobile dealership
used car dealers|preowned car dealer|used auto sales|independent car lot
auto parts stores|automotive parts|car parts supplier|truck parts store
parking lot striping|line striping contractor|pavement marking|parking lot painting
courier services|local courier|same day delivery|messenger service
freight brokers|freight brokerage|transportation broker|shipping broker
trucking companies|trucking company|freight carrier|transport company
logistics companies|logistics provider|third party logistics|3PL company
limousine services|limo service|chauffeur service|executive car service
taxi services|cab company|taxi company|local cab
charter bus companies|bus charter|motor coach rental|group transportation
airport shuttle services|airport transfer|shuttle company|airport transportation
bicycle repair|bike repair shop|cycle service|mobile bike repair
e-bike shops|electric bike shop|e-bike dealer|electric bicycle repair
accountants|accounting firm|certified public accountant|CPA firm
bookkeepers|bookkeeping service|small business bookkeeping|virtual bookkeeper
tax preparation|tax preparer|tax service|income tax filing
payroll services|payroll company|payroll provider|payroll processing
financial advisors|financial planner|wealth advisor|investment advisor
insurance agencies|insurance agent|independent insurance agency|commercial insurance broker
mortgage brokers|mortgage broker|home loan broker|mortgage company
real estate agents|realtor|real estate broker|property agent
property management|property manager|rental management|residential property management
commercial real estate brokers|commercial realtor|commercial property broker|CRE brokerage
home inspectors|home inspection|property inspector|residential inspector
appraisers|real estate appraiser|property appraisal|valuation service
title companies|title agency|real estate title service|title insurance company
escrow services|escrow company|settlement service|closing company
lawyers|law firm|attorney|legal practice
family law firms|family lawyer|divorce attorney|child custody lawyer
personal injury lawyers|injury attorney|accident lawyer|personal injury law firm
immigration lawyers|immigration attorney|visa lawyer|immigration law firm
criminal defense lawyers|criminal attorney|defense lawyer|DUI attorney
estate planning lawyers|estate attorney|probate lawyer|trust attorney
employment lawyers|labor attorney|workplace lawyer|employment law firm
business consultants|business consulting firm|small business consultant|growth consultant
management consultants|management consulting firm|operations consultant|strategy consultant
HR consultants|human resources consultant|HR advisory|people operations consultant
recruiting agencies|recruiter|executive search firm|talent acquisition agency
staffing agencies|staffing company|temporary employment agency|workforce agency
virtual assistants|virtual assistant service|remote administrative assistant|online assistant
call centers|call center service|contact center|answering service
translation services|translation agency|language service provider|interpreter service
notary services|notary public|mobile notary|notary signing agent
marketing agencies|digital marketing agency|advertising agency|growth marketing firm
SEO agencies|SEO company|search engine optimization agency|local SEO service
PPC agencies|paid search agency|Google Ads agency|pay per click management
social media agencies|social media marketing|social media management|content marketing agency
web design agencies|web designer|website design company|web development agency
software development agencies|software company|custom software developer|app development agency
IT support companies|IT services|computer support company|business IT support
managed service providers|managed IT provider|MSP company|outsourced IT
cybersecurity consultants|cybersecurity company|information security consultant|security assessment firm
cloud consultants|cloud consulting company|cloud migration service|AWS consultant
telecom providers|business telecom company|VoIP provider|communications service
graphic designers|graphic design studio|freelance designer|branding designer
photographers|professional photographer|commercial photographer|portrait photographer
videographers|video production company|commercial videographer|wedding videographer
printing companies|commercial printer|print shop|digital printing service
sign companies|sign maker|commercial signage|custom sign shop
promotional products|branded merchandise supplier|corporate gifts|promo items company
public relations agencies|PR agency|communications firm|media relations agency
event planners|event planning company|corporate event planner|party planner
wedding planners|wedding coordinator|bridal planner|wedding planning service
dentists|dentist|dental clinic|general dentistry
orthodontists|orthodontist|braces clinic|orthodontic practice
oral surgeons|oral surgery practice|maxillofacial surgeon|dental implant surgeon
pediatric dentists|children's dentist|kids dental clinic|pediatric dental practice
doctors|physician|medical doctor|medical practice
medical clinics|health clinic|primary care clinic|outpatient clinic
urgent care centers|urgent care clinic|walk in clinic|immediate care center
chiropractors|chiropractor|chiropractic clinic|chiropractic care
physical therapists|physical therapy clinic|physiotherapist|rehabilitation therapy
occupational therapists|occupational therapy clinic|OT practice|rehabilitation therapist
speech therapists|speech therapy clinic|speech language pathologist|speech pathology practice
psychologists|psychologist|psychology practice|clinical psychologist
psychiatrists|psychiatrist|psychiatric clinic|mental health physician
counselors|counseling practice|licensed counselor|mental health counseling
addiction treatment centers|rehab center|substance abuse treatment|recovery center
home health agencies|home healthcare|in home nursing|home care agency
nursing homes|skilled nursing facility|long term care facility|convalescent home
assisted living facilities|assisted living community|senior living facility|residential care home
hospice providers|hospice care|end of life care|palliative care provider
optometrists|optometrist|eye doctor|vision clinic
ophthalmologists|ophthalmologist|eye surgery clinic|medical eye care
hearing aid centers|audiologist|hearing clinic|hearing aid provider
podiatrists|podiatrist|foot doctor|foot and ankle clinic
dermatologists|dermatologist|skin clinic|dermatology practice
plastic surgeons|plastic surgery clinic|cosmetic surgeon|aesthetic surgery practice
medical spas|med spa|aesthetic clinic|cosmetic treatment clinic
massage therapists|massage therapy|therapeutic massage|mobile massage therapist
acupuncturists|acupuncture clinic|Chinese medicine practitioner|acupuncture practice
nutritionists|nutrition consultant|nutrition coach|wellness nutritionist
dietitians|registered dietitian|dietitian practice|medical nutrition therapy
personal trainers|fitness trainer|private trainer|personal training studio
gyms|fitness center|health club|workout gym
yoga studios|yoga classes|yoga center|yoga instructor
pilates studios|pilates classes|reformer pilates|pilates instructor
martial arts schools|karate school|jiu jitsu academy|martial arts academy
pharmacies|pharmacy|drugstore|community pharmacy
medical laboratories|clinical laboratory|medical testing lab|diagnostic laboratory
diagnostic imaging centers|radiology center|MRI center|medical imaging clinic
veterinarians|veterinarian|veterinary clinic|animal doctor
animal hospitals|veterinary hospital|pet hospital|emergency vet
restaurants|restaurant|dining establishment|local eatery
cafes|coffee shop|cafe|espresso bar
bakeries|bakery|bake shop|artisan bread shop
caterers|catering company|event catering|corporate caterer
food trucks|mobile food vendor|food trailer|street food truck
bars|pub|cocktail bar|tavern
hotels|hotel|lodging|boutique hotel
wedding venues|event venue|reception venue|wedding hall
pet groomers|pet grooming|dog groomer|mobile pet grooming
dog trainers|dog training|canine trainer|obedience school
"""


def _group(index: int) -> str:
    if index < 70:
        return "home_property"
    if index < 100:
        return "automotive_logistics"
    if index < 150:
        return "professional_business"
    if index < 190:
        return "health_wellness"
    return "hospitality_specialty"


def entries() -> list[dict]:
    result = []
    for index, raw in enumerate(line for line in _ROWS.splitlines() if line.strip()):
        values = [re.sub(r"\s+", " ", value).strip() for value in raw.split("|")]
        result.append(
            {
                "name": values[0],
                "synonyms": list(dict.fromkeys(values)),
                "group": _group(index),
            }
        )
    if len(result) != 200:
        raise RuntimeError(f"Niche catalog must contain exactly 200 entries, found {len(result)}")
    return result


def lookup(name: str) -> dict | None:
    wanted = re.sub(r"\s+", " ", str(name or "")).strip().casefold()
    for entry in entries():
        if wanted == entry["name"].casefold() or wanted in {
            term.casefold() for term in entry["synonyms"]
        }:
            return entry
    return None

