import About from '../components/About'
import ConnectorOrbit from '../components/ConnectorOrbit'
import CTA from '../components/CTA'
import Features from '../components/Features'
import Hero from '../components/Hero'
import HowItWorks from '../components/HowItWorks'
import QuoteCircles from '../components/QuoteCircles'
import ScrollReveal from '../components/ScrollReveal'
import Testimonials from '../components/Testimonials'

export default function LandingPage() {
  return (
    <>
      <Hero />
      <About />
      <ScrollReveal />
      <Features />
      <ConnectorOrbit />
      <HowItWorks />
      <QuoteCircles />
      <Testimonials />
      <CTA />
    </>
  )
}
